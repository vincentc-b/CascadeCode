"""Epic Team mint_feature and list_children."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.epic.mint  # noqa: F401 — registers tools
from cascade.board.store import list_board, read_doc, reset_id_reservations, write_doc
from cascade.epic.guard import EpicToolDenied, tool_guard
from cascade.epic.mint import list_children, mint_feature
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo

_REQUIRED_FEATURE_HEADINGS = (
    "Parent Epic",
    "Scope",
    "Data structures",
    "API contracts",
    "Logic flow",
    "Task breakdown",
    "Risks & upward questions",
    "Decision log",
)


@pytest.fixture(autouse=True)
def _reset_ids() -> None:
    reset_id_reservations()
    yield
    reset_id_reservations()


@pytest.fixture
def epic_board(tmp_path: Path) -> dict[str, object]:
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_001", title="Functional MVP", tier="epic", status="active")
    existing = add_doc(
        root,
        id="feat_001",
        title="Existing",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    epic = read_doc("epic_001", root=root)
    epic.meta.children = ["feat_001"]
    write_doc(epic, root=root)
    task = add_doc(
        root,
        id="task_001",
        title="Stray task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    return {"root": root, "epic": epic, "existing": existing, "task": task}


def test_mint_creates_backlog_feature_with_headings(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    feature_id = mint_feature("New capability", body_stub="Ship it.", epic_id="epic_001", root=root)
    doc = read_doc(feature_id, root=root)
    assert doc.meta.status == "backlog"
    assert doc.meta.parent == "epic_001"
    assert doc.meta.path.parent.name == "1_backlog"
    assert doc.meta.path.is_file()
    assert "Ship it." in doc.body
    found = {line[3:].strip() for line in doc.body.splitlines() if line.startswith("## ")}
    assert set(_REQUIRED_FEATURE_HEADINGS) <= found
    parent_section = doc.body.split("## Parent Epic")[1].split("##")[0]
    assert "epic_001" in parent_section


def test_mint_updates_epic_children_and_breakdown(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    first = mint_feature("One", epic_id="epic_001", root=root)
    epic = read_doc("epic_001", root=root)
    assert first in epic.meta.children
    assert f"- {first}" in epic.body

    second = mint_feature("Two", epic_id="epic_001", root=root)
    epic = read_doc("epic_001", root=root)
    assert epic.meta.children == ["feat_001", first, second]
    assert f"- {second}" in epic.body


def test_mint_emits_feature_minted_event(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    feature_id = mint_feature("Evented", epic_id="epic_001", root=root)
    events, _ = read_events("epic_001", 0, root=root)
    minted = [e for e in events if e.type == "FeatureMinted"]
    assert len(minted) == 1
    assert minted[0].dest == "epic_001"
    assert minted[0].payload == {"feature_id": feature_id, "epic_id": "epic_001"}
    assert minted[0].ts.tzinfo is not None


def test_mint_stays_in_backlog_not_active(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    feature_id = mint_feature("Backlog only", epic_id="epic_001", root=root)
    doc = read_doc(feature_id, root=root)
    assert "2_active" not in str(doc.meta.path)
    assert doc.meta.status == "backlog"


def test_list_children_returns_features_only(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    epic = read_doc("epic_001", root=root)
    epic.meta.children = ["feat_001", "task_001", "missing_999"]
    write_doc(epic, root=root)
    minted = mint_feature("Listed", epic_id="epic_001", root=root)

    children = list_children(epic_id="epic_001", root=root)
    ids = [m.id for m in children]
    assert ids == ["feat_001", minted]
    assert all(m.tier == "feature" for m in children)


def test_mint_copies_depends_on(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    feature_id = mint_feature(
        "Depends",
        depends_on=["feat_001"],
        epic_id="epic_001",
        root=root,
    )
    doc = read_doc(feature_id, root=root)
    assert doc.meta.depends_on == ["feat_001"]


def test_mint_rejects_unknown_dep(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    with pytest.raises(EpicToolDenied):
        mint_feature("Bad dep", depends_on=["feat_missing"], epic_id="epic_001", root=root)


def test_mint_rejects_task_dep(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    with pytest.raises(EpicToolDenied):
        mint_feature("Bad dep", depends_on=["task_001"], epic_id="epic_001", root=root)


def test_mint_rejects_epic_dep(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    with pytest.raises(EpicToolDenied):
        mint_feature("Bad dep", depends_on=["epic_001"], epic_id="epic_001", root=root)


def test_mint_rejects_non_epic_id(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    with pytest.raises(EpicToolDenied):
        mint_feature("Nope", epic_id="feat_001", root=root)


def test_tasks_path_write_denied_by_guard(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    task_path = epic_board["task"].meta.path  # type: ignore[union-attr]
    assert not tool_guard(task_path, "write", epic_id="epic_001", root=root)


def test_mint_module_has_no_dispatch_symbols() -> None:
    text = Path(__file__).resolve().parents[2].joinpath("cascade/epic/mint.py").read_text(
        encoding="utf-8"
    )
    for symbol in ("move_doc", "dispatch_feature", "dispatch_task", "activate_epic"):
        assert symbol not in text


def test_unknown_epic_raises(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    with pytest.raises(EpicToolDenied):
        mint_feature("X", epic_id="epic_404", root=root)


def test_board_lists_minted_feature(epic_board: dict[str, object]) -> None:
    root = epic_board["root"]
    before = len(list_board(root).by_id)
    feature_id = mint_feature("Indexed", epic_id="epic_001", root=root)
    board = list_board(root)
    assert feature_id in board.by_id
    assert len(board.by_id) == before + 1
