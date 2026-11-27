"""Feature Team mint_task."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cascade.feature.mint  # noqa: F401 — registers tools
from cascade.board.store import (
    list_board,
    move_doc,
    read_doc,
    reset_id_reservations,
    write_doc,
)
from cascade.board.validate import _REQUIRED_HEADINGS
from cascade.comments.store import comment
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.mint import mint_task
from cascade.feature.repair import admit_feature_repair
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


def test_mint_creates_backlog_task_with_headings(
    feature_board: dict[str, object],
) -> None:
    root = feature_board["root"]
    task_id = mint_task(
        "New work", body_stub="Do the thing.", feature_id="feat_001", root=root
    )
    doc = read_doc(task_id, root=root)
    assert doc.meta.status == "backlog"
    assert doc.meta.parent == "feat_001"
    assert doc.meta.owners == ["swe"]
    assert doc.meta.path.parent.name == "1_backlog"
    assert doc.meta.path.is_file()
    assert "Do the thing." in doc.body
    found = {
        line[3:].strip() for line in doc.body.splitlines() if line.startswith("## ")
    }
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


def test_mint_updates_feature_children_and_breakdown(
    feature_board: dict[str, object],
) -> None:
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


def test_mint_refuses_open_blocking_human_comment(
    feature_board: dict[str, object],
) -> None:
    root = feature_board["root"]
    cmt_id = comment(
        "feat_001",
        "Scope",
        "Stop minting",
        blocking=True,
        author="human",
        root=root,
    )
    with pytest.raises(FeatureToolDenied) as exc_info:
        mint_task("Blocked", feature_id="feat_001", root=root)
    message = str(exc_info.value)
    assert cmt_id in message
    assert "/plan/feat_001#plan-comments" in message


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
    resolve_comment("feat_001", cmt_id, author="human", root=root)
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
        mint_task(
            "Bad skills", skills=["../outside.txt"], feature_id="feat_001", root=root
        )


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


def test_mint_sets_parent_rev_from_feature_head(
    feature_board: dict[str, object],
) -> None:
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
        mint_task(
            "Bad dep", depends_on=[foreign.meta.id], feature_id="feat_001", root=root
        )


def test_mint_module_has_no_dispatch_symbols() -> None:
    text = (
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("cascade/feature/mint.py")
        .read_text(encoding="utf-8")
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


def _admitted_late_mint(root: Path, request_id: str = "mint:repair-1") -> None:
    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = datetime.now(timezone.utc)
    write_doc(feature, root=root)
    move_doc("feat_001", "completed", root=root)
    admit_feature_repair("feat_001", request_id, root=root)


def test_late_mint_replays_one_reserved_child(feature_board: dict[str, object]) -> None:
    root = feature_board["root"]
    _admitted_late_mint(root)

    first = mint_task(
        "Late repair",
        feature_id="feat_001",
        repair_request_id="mint:repair-1",
        root=root,
    )
    replay = mint_task(
        "Late repair",
        feature_id="feat_001",
        repair_request_id="mint:repair-1",
        root=root,
    )

    assert replay == first
    feature = read_doc("feat_001", root=root)
    assert feature.meta.children.count(first) == 1
    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "TasksMinted" for event in events) == 1


def test_late_mint_resumes_after_reserved_child_write_failure(
    feature_board: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = feature_board["root"]
    _admitted_late_mint(root, "mint:crash-gap")
    real_write = cascade.feature.mint.write_doc
    failed = False

    def fail_once(doc, *, root):
        nonlocal failed
        if doc.meta.tier == "task" and not failed:
            failed = True
            raise OSError("injected child write failure")
        return real_write(doc, root=root)

    monkeypatch.setattr(cascade.feature.mint, "write_doc", fail_once)
    with pytest.raises(OSError, match="injected"):
        mint_task(
            "Crash-safe repair",
            feature_id="feat_001",
            repair_request_id="mint:crash-gap",
            root=root,
        )
    ledger = json.loads((root / ".cascade/executions.json").read_text())
    action = next(
        row
        for row in ledger["actions"].values()
        if row.get("request_id") == "mint:crash-gap"
    )
    reserved = action["reserved_task_id"]

    assert (
        mint_task(
            "Crash-safe repair",
            feature_id="feat_001",
            repair_request_id="mint:crash-gap",
            root=root,
        )
        == reserved
    )
    assert read_doc(reserved, root=root).meta.parent == "feat_001"


def test_late_mint_resumes_after_parent_write_checkpoint_gap(
    feature_board: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = feature_board["root"]
    _admitted_late_mint(root, "mint:parent-gap")
    real_write = cascade.feature.mint.feature_write_doc
    failed = False

    def write_then_interrupt(*args, **kwargs):
        nonlocal failed
        result = real_write(*args, **kwargs)
        if not failed:
            failed = True
            raise OSError("injected parent checkpoint gap")
        return result

    monkeypatch.setattr(cascade.feature.mint, "feature_write_doc", write_then_interrupt)
    with pytest.raises(OSError, match="parent checkpoint gap"):
        mint_task(
            "Parent-gap repair",
            feature_id="feat_001",
            repair_request_id="mint:parent-gap",
            root=root,
        )

    replay = mint_task(
        "Parent-gap repair",
        feature_id="feat_001",
        repair_request_id="mint:parent-gap",
        root=root,
    )
    feature = read_doc("feat_001", root=root)
    assert feature.meta.children.count(replay) == 1
    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "TasksMinted" for event in events) == 1


def test_late_mint_changed_content_after_reservation_refuses(
    feature_board: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = feature_board["root"]
    _admitted_late_mint(root, "mint:changed")
    real_write = cascade.feature.mint.write_doc

    def interrupt_task_write(doc, *, root):
        if doc.meta.tier == "task":
            raise OSError("injected reserved gap")
        return real_write(doc, root=root)

    monkeypatch.setattr(cascade.feature.mint, "write_doc", interrupt_task_write)
    with pytest.raises(OSError, match="reserved gap"):
        mint_task(
            "Original repair",
            feature_id="feat_001",
            repair_request_id="mint:changed",
            root=root,
        )
    monkeypatch.setattr(cascade.feature.mint, "write_doc", real_write)

    with pytest.raises(FeatureToolDenied, match="specification changed"):
        mint_task(
            "Changed repair",
            feature_id="feat_001",
            repair_request_id="mint:changed",
            root=root,
        )


def test_concurrent_late_mint_joins_one_reserved_child(
    feature_board: dict[str, object],
) -> None:
    root = feature_board["root"]
    _admitted_late_mint(root, "mint:concurrent")

    def mint() -> str:
        return mint_task(
            "Concurrent repair",
            feature_id="feat_001",
            repair_request_id="mint:concurrent",
            root=root,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        task_ids = list(pool.map(lambda _: mint(), range(2)))

    assert task_ids[0] == task_ids[1]
    feature = read_doc("feat_001", root=root)
    assert feature.meta.children.count(task_ids[0]) == 1
    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "TasksMinted" for event in events) == 1


def test_repair_generation_requires_its_request_identity(
    feature_board: dict[str, object],
) -> None:
    root = feature_board["root"]
    _admitted_late_mint(root)
    with pytest.raises(FeatureToolDenied, match="requires repair_request_id"):
        mint_task("Unfenced repair", feature_id="feat_001", root=root)
