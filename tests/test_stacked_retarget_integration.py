"""Native retarget verification and stacked-flow regressions (task_007_001_003)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.stacked_dispatch import (
    feature_stacked_dispatch_view,
    persist_feature_dispatch_selection,
    read_feature_dispatch_selection,
    reconcile_stacked_native_retargeting,
    FeatureDispatchSelection,
)
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.watchdog.dispatch import dispatch_feature
from cascade.workspace.integration_worktree import integration_branch
from tests.support import add_doc, approve_board_feature, make_repo


def _activate_and_open_epic(root: Path, epic_id: str = "epic_001") -> None:
    from cascade.watchdog.dispatch import activate_epic

    add_doc(root, id=epic_id, title="Epic", tier="epic", status="ready_to_plan")
    assert activate_epic(epic_id, "human", root=root).ok


def _seed_review(
    root: Path,
    feature_id: str,
    *,
    epic_id: str = "epic_001",
    target_branch: str | None = None,
    closed: bool = False,
) -> None:
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
        "target_branch": target_branch or integration_branch("epic", epic_id),
        "draft": False,
        "closed": closed,
    }
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _seed_dispatch_stack(
    root: Path, downstream_id: str, predecessor_id: str, *, epic_id: str = "epic_001"
) -> None:
    persist_feature_dispatch_selection(
        FeatureDispatchSelection(
            feature_id=downstream_id,
            base_branch=integration_branch("feature", predecessor_id),
            predecessor_id=predecessor_id,
        ),
        root=root,
    )
    _seed_review(
        root,
        downstream_id,
        epic_id=epic_id,
        target_branch=integration_branch("feature", predecessor_id),
    )


def test_native_retarget_reconciles_dispatch_and_registry(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
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
        status="active",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_review(root, "feat_001", closed=True)
    _seed_dispatch_stack(root, "feat_002", "feat_001")
    epic_base = integration_branch("epic", "epic_001")

    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_a, **_k: {"state": "open", "comments": [], "target_branch": epic_base},
    )

    first = reconcile_stacked_native_retargeting(root)
    assert first["reconciled"] == ["feat_002"]
    assert first["stale"] == []
    selection = read_feature_dispatch_selection("feat_002", root=root)
    assert selection is not None
    assert selection.predecessor_id is None
    assert selection.base_branch == epic_base
    reviews = json.loads((root / ".cascade" / "reviews.json").read_text(encoding="utf-8"))
    assert reviews["feat_002"]["target_branch"] == epic_base
    view = feature_stacked_dispatch_view("feat_002", root=root)
    assert view is not None
    assert view["retarget_state"] == "reconciled"

    second = reconcile_stacked_native_retargeting(root)
    assert second["reconciled"] == []
    assert second["stale"] == []


def test_stale_base_surfaces_diagnostic_without_mutating_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
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
        status="active",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_review(root, "feat_001", closed=True)
    pred_base = integration_branch("feature", "feat_001")
    _seed_dispatch_stack(root, "feat_002", "feat_001")
    before = (root / ".cascade" / "reviews.json").read_text(encoding="utf-8")

    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_a, **_k: {"state": "open", "comments": [], "target_branch": pred_base},
    )

    result = reconcile_stacked_native_retargeting(root)
    assert result["stale"] == ["feat_002"]
    assert (root / ".cascade" / "reviews.json").read_text(encoding="utf-8") == before
    view = feature_stacked_dispatch_view("feat_002", root=root)
    assert view is not None
    assert view["retarget_state"] == "stale_base"
    assert view["retarget_expected_base"] == integration_branch("epic", "epic_001")
    assert view["retarget_actual_base"] == pred_base


def test_missing_live_identity_fails_closed(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
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
        status="active",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_review(root, "feat_001", closed=True)
    _seed_dispatch_stack(root, "feat_002", "feat_001")

    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no forge call expected")),
    )
    monkeypatch.setattr(
        "cascade.review.live_merge_request_target_branch",
        lambda *_a, **_k: None,
    )

    result = reconcile_stacked_native_retargeting(root)
    assert result["blocked"] == ["feat_002"]
    view = feature_stacked_dispatch_view("feat_002", root=root)
    assert view is not None
    assert view["retarget_state"] == "missing_pr_identity"


def test_three_feature_chain_uses_direct_predecessor(tmp_path: Path) -> None:
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
        _seed_review(root, fid)
    add_doc(
        root,
        id="feat_003",
        title="Third",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_002"],
    )
    approve_board_feature(root, "feat_003")

    assert dispatch_feature("feat_003", "human", root=root).ok
    selection = read_feature_dispatch_selection("feat_003", root=root)
    assert selection is not None
    assert selection.predecessor_id == "feat_002"
    assert selection.base_branch == integration_branch("feature", "feat_002")


def test_disabling_stacked_does_not_rewrite_existing_pr(tmp_path: Path) -> None:
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
    _seed_predecessor = integration_branch("feature", "feat_001")
    _seed_review(root, "feat_001")
    approve_board_feature(root, "feat_002")
    assert dispatch_feature("feat_002", "human", root=root).ok
    _seed_review(
        root,
        "feat_002",
        target_branch=_seed_predecessor,
    )
    before = (root / ".cascade" / "reviews.json").read_text(encoding="utf-8")

    write_stacked_pr_enabled("epic_001", False, root=root)
    from cascade.board.store import move_doc

    move_doc("feat_002", "completed", root=root)
    add_doc(
        root,
        id="feat_003",
        title="Third",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_002"],
    )
    approve_board_feature(root, "feat_003")
    blocked = dispatch_feature("feat_003", "human", root=root)
    assert blocked.ok is False
    assert blocked.reason == "feature_awaiting_merge"
    assert (root / ".cascade" / "reviews.json").read_text(encoding="utf-8") == before


def test_completion_reconcile_runs_native_retarget(tmp_path: Path, monkeypatch) -> None:
    from cascade.completion_reconcile import reconcile_completion

    root = make_repo(tmp_path, git=False)
    _activate_and_open_epic(root)
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
        status="active",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_review(root, "feat_001", closed=True)
    _seed_dispatch_stack(root, "feat_002", "feat_001")
    epic_base = integration_branch("epic", "epic_001")
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_a, **_k: {"state": "open", "comments": [], "target_branch": epic_base},
    )

    reconcile_completion(root)
    selection = read_feature_dispatch_selection("feat_002", root=root)
    assert selection is not None
    assert selection.base_branch == epic_base
