"""Stacked PR dispatch selection and durable PR identity (task_007_001_002)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.board.store import move_doc, read_doc
from cascade.stacked_dispatch import read_feature_dispatch_selection
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.watchdog.dispatch import dispatch_feature
from cascade.workspace.integration_worktree import integration_branch
from tests.support import add_doc, approve_board_feature, make_repo


def _activate_and_open_epic(root: Path, epic_id: str = "epic_001") -> None:
    from cascade.watchdog.dispatch import activate_epic

    add_doc(root, id=epic_id, title="Epic", tier="epic", status="ready_to_plan")
    assert activate_epic(epic_id, "human", root=root).ok


def _seed_predecessor_review(root: Path, feature_id: str, *, epic_id: str = "epic_001") -> None:
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, object] = {}
    if path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
    state[feature_id] = {
        "url": f"https://github.example/o/r/pull/{feature_id}",
        "number": "1",
        "forge": "github",
        "source_branch": integration_branch("feature", feature_id),
        "target_branch": integration_branch("epic", epic_id),
        "draft": False,
        "closed": False,
    }
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_disabled_path_retains_merge_gate(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", False, root=root)
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(root, id="feat_002", title="Second", tier="feature", parent="epic_001", depends_on=["feat_001"])
    _seed_predecessor_review(root, "feat_001")
    approve_board_feature(root, "feat_002")

    result = dispatch_feature("feat_002", "human", root=root)
    assert result.ok is False
    assert result.reason == "feature_awaiting_merge"


def test_stacked_allows_unmerged_predecessor_and_persists_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_predecessor_review(root, "feat_001")
    approve_board_feature(root, "feat_002")

    result = dispatch_feature("feat_002", "human", root=root)
    assert result.ok is True
    selection = read_feature_dispatch_selection("feat_002", root=root)
    assert selection is not None
    assert selection.predecessor_id == "feat_001"
    assert selection.base_branch == integration_branch("feature", "feat_001")


def test_first_feature_uses_epic_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")

    assert dispatch_feature("feat_001", "human", root=root).ok
    selection = read_feature_dispatch_selection("feat_001", root=root)
    assert selection is not None
    assert selection.predecessor_id is None
    assert selection.base_branch == integration_branch("epic", "epic_001")


def test_merged_predecessor_falls_back_to_epic_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/o/r/pull/1",
                    "number": "1",
                    "forge": "github",
                    "source_branch": integration_branch("feature", "feat_001"),
                    "target_branch": integration_branch("epic", "epic_001"),
                    "draft": False,
                    "closed": True,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    approve_board_feature(root, "feat_002")

    assert dispatch_feature("feat_002", "human", root=root).ok
    selection = read_feature_dispatch_selection("feat_002", root=root)
    assert selection is not None
    assert selection.predecessor_id is None
    assert selection.base_branch == integration_branch("epic", "epic_001")


def test_fan_in_fails_closed(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    for fid in ("feat_001", "feat_002"):
        add_doc(
            root,
            id=fid,
            title=fid,
            tier="feature",
            status="completed",
            parent="epic_001",
        )
        _seed_predecessor_review(root, fid)
    add_doc(
        root,
        id="feat_003",
        title="Join",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001", "feat_002"],
    )
    approve_board_feature(root, "feat_003")

    result = dispatch_feature("feat_003", "human", root=root)
    assert result.ok is False
    assert result.reason == "unsupported_topology"


def test_missing_predecessor_identity_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    approve_board_feature(root, "feat_002")

    result = dispatch_feature("feat_002", "human", root=root)
    assert result.ok is False
    assert result.reason == "missing_predecessor_pr_identity"


def test_completion_rejects_without_pr_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cascade.board.errors import SchemaError

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)

    with pytest.raises(SchemaError, match="feature_pull_request_required"):
        move_doc("feat_001", "completed", root=root)


def test_dispatch_selection_idempotent_on_retry(tmp_path: Path) -> None:
    from cascade.board.types import BoardIndex
    from cascade.stacked_dispatch import ensure_feature_dispatch_selection

    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    meta = read_doc("feat_001", root=root).meta
    epic_meta = read_doc("epic_001", root=root).meta
    board = BoardIndex(by_id={"feat_001": meta, "epic_001": epic_meta})

    first = ensure_feature_dispatch_selection("feat_001", meta, board, root=root)
    second = ensure_feature_dispatch_selection("feat_001", meta, board, root=root)
    assert first.ok and second.ok
    assert first.selection == second.selection


def test_feature_room_override_disables_stacked(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
    write_stacked_pr_enabled("epic_001", True, root=root)
    write_stacked_pr_enabled("feat_002", False, root=root)
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_predecessor_review(root, "feat_001")
    approve_board_feature(root, "feat_002")

    result = dispatch_feature("feat_002", "human", root=root)
    assert result.ok is False
    assert result.reason == "feature_awaiting_merge"
