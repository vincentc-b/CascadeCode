"""Feature Team mint_task."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.feature.mint  # noqa: F401 — registers tools
from cascade.board.store import list_board, read_doc, reset_id_reservations, write_doc
from cascade.board.validate import _REQUIRED_HEADINGS
from cascade.comments.store import comment
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.mint import mint_task
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _reset_ids() -> None:
    reset_id_reservations()
    yield
    reset_id_reservations()


@pytest.fixture
def feature_board(tmp_path: Path) -> dict[str, object]:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    feature = add_doc(
        root,
        id="feat_001",
        title="Mine",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    sibling_task = add_doc(
        root,
        id="task_001",
        title="Existing",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    feature = read_doc("feat_001", root=root)
    feature.meta.children = ["task_001"]
    write_doc(feature, root=root)
    (root / "cascade.toml").write_text("task_parallelism = 1\n", encoding="utf-8")
    return {"root": root, "feature": feature, "sibling_task": sibling_task}


def test_mint_creates_backlog_task_with_headings(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    task_id = mint_task("New work", body_stub="Do the thing.", feature_id="feat_001", root=root)
    doc = read_doc(task_id, root=root)
    assert doc.meta.status == "backlog"
    assert doc.meta.parent == "feat_001"
    assert doc.meta.owners == ["swe"]
    assert doc.meta.path.parent.name == "1_backlog"
    assert doc.meta.path.is_file()
    assert "Do the thing." in doc.body
    found = {line[3:].strip() for line in doc.body.splitlines() if line.startswith("## ")}
    assert set(_REQUIRED_HEADINGS["task"]) <= found
    assert "feat_001" in doc.body.split("## Parent Feature")[1].split("##")[0]


def test_mint_copies_depends_on_into_body(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    task_id = mint_task(
        "Depends",
        depends_on=["task_001"],
        feature_id="feat_001",
        root=root,
    )
    doc = read_doc(task_id, root=root)
    assert doc.meta.depends_on == ["task_001"]
    deps_section = doc.body.split("## Depends on")[1].split("##")[0]
    assert "task_001" in deps_section


def test_mint_updates_feature_children_and_breakdown(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    first = mint_task("One", feature_id="feat_001", root=root)
    feature = read_doc("feat_001", root=root)
    assert first in feature.meta.children
    assert f"- {first}" in feature.body

    second = mint_task("Two", feature_id="feat_001", root=root)
    feature = read_doc("feat_001", root=root)
    assert feature.meta.children == ["task_001", first, second]
    assert f"- {second}" in feature.body


def test_mint_emits_tasks_minted_event(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    task_id = mint_task("Evented", feature_id="feat_001", root=root)
    events, _ = read_events("feat_001", 0, root=root)
    minted = [e for e in events if e.type == "TasksMinted"]
    assert len(minted) == 1
    assert minted[0].dest == "feat_001"
    assert minted[0].payload == {"feature_id": "feat_001", "task_ids": [task_id]}
    assert minted[0].ts.tzinfo is not None


def test_mint_refuses_open_blocking_human_comment(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    comment(
        "feat_001",
        "Scope",
        "Stop minting",
        blocking=True,
        author="human",
        root=root,
    )
    with pytest.raises(FeatureToolDenied, match="blocking human comment"):
        mint_task("Blocked", feature_id="feat_001", root=root)


def test_mint_allows_blocking_when_resolved(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    from cascade.comments.store import resolve_comment

    cmt_id = comment(
        "feat_001",
        "Scope",
        "Was blocking",
        blocking=True,
        author="human",
        root=root,
    )
    resolve_comment("feat_001", cmt_id, root=root)
    task_id = mint_task("After resolve", feature_id="feat_001", root=root)
    assert task_id.startswith("task_")


def test_mint_accepts_in_repo_skill_path_not_yet_on_disk(
    feature_board: dict[str, object],
) -> None:
    root = feature_board["root"]
    skill = "docs/skills/future_skill.md"
    task_id = mint_task(
        "Future skill",
        skills=[skill],
        feature_id="feat_001",
        root=root,
    )
    doc = read_doc(task_id, root=root)
    assert [p.as_posix() for p in doc.meta.skills] == [skill]
    assert skill in doc.body.split("## Skills")[1]
    assert not (root / skill).exists()


def test_mint_rejects_skill_outside_repo(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    with pytest.raises(FeatureToolDenied, match="not inside the repo"):
        mint_task("Bad skills", skills=["../outside.txt"], feature_id="feat_001", root=root)


def test_mint_accepts_in_repo_skill_path(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    task_id = mint_task(
        "With skill",
        skills=["cascade.toml"],
        feature_id="feat_001",
        root=root,
    )
    doc = read_doc(task_id, root=root)
    assert [p.as_posix() for p in doc.meta.skills] == ["cascade.toml"]
    assert "cascade.toml" in doc.body.split("## Skills")[1]


def test_mint_stays_in_backlog(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    task_id = mint_task("Backlog only", feature_id="feat_001", root=root)
    doc = read_doc(task_id, root=root)
    assert "2_active" not in str(doc.meta.path)
    assert doc.meta.status == "backlog"


def test_mint_sets_parent_rev_from_feature_head(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    feature = read_doc("feat_001", root=root)
    task_id = mint_task("Pinned", feature_id="feat_001", root=root)
    doc = read_doc(task_id, root=root)
    assert doc.meta.parent_rev == feature.sha
    if feature.sha is not None:
        assert len(doc.meta.parent_rev) == 40


def test_mint_rejects_foreign_task_dep(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    add_doc(
        root,
        id="feat_002",
        title="Other",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    foreign = add_doc(
        root,
        id="task_002",
        title="Foreign",
        tier="task",
        status="backlog",
        parent="feat_002",
    )
    with pytest.raises(FeatureToolDenied, match="not owned"):
        mint_task("Bad dep", depends_on=[foreign.meta.id], feature_id="feat_001", root=root)


def test_mint_module_has_no_dispatch_symbols() -> None:
    text = Path(__file__).resolve().parents[2].joinpath("cascade/feature/mint.py").read_text(
        encoding="utf-8"
    )
    for symbol in ("move_doc", "dispatch_feature", "dispatch_task", "activate_epic"):
        assert symbol not in text


def test_board_lists_minted_task(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    before = len(list_board(root).by_id)
    task_id = mint_task("Indexed", feature_id="feat_001", root=root)
    board = list_board(root)
    assert task_id in board.by_id
    assert len(board.by_id) == before + 1
