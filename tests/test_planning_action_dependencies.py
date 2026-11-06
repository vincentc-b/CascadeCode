"""Fresh dependency evidence at planning action boundaries."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.approvals import approve_epic_plan, approve_feature
from cascade.board.store import list_board, move_doc, read_doc
from cascade.epic.mint import mint_feature
from cascade.epic.plan_readiness import compute_epic_plan_readiness
from cascade.epic.planning_signoffs import (
    canonical_plan_revision,
    read_plan_sign_offs,
    sign_off_epic_plan,
)
from cascade.planning_action_dependencies import (
    DependencyActionRefused,
    evaluate_action_dependencies,
)
from cascade.watchdog import dispatch_feature
from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
from cascade.war_room.server import WarRoomRequestHandler
from tests.support import add_doc, make_repo, sign_off_both_planning_roles


class _ApprovalHandler:
    def __init__(self, root: Path) -> None:
        self.server = SimpleNamespace(root=root)
        self.responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def _require_work_id(self, body: dict[str, object]) -> str | None:
        work_id = body.get("id")
        return work_id if isinstance(work_id, str) else None

    def _json_response(
        self, status: HTTPStatus, payload: dict[str, object]
    ) -> None:
        self.responses.append((status, payload))

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        self._json_response(status, {"error": message})


def test_action_refresh_ignores_cached_and_request_scoped_board(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Dependency", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    stale = merged_board(root)
    move_doc("epic_001", "completed", root=root)

    with merged_board_snapshot(root, stale):
        assert merged_board(root) is stale
        assert evaluate_action_dependencies("epic_002", root=root).outcome == "satisfied"


def test_sign_off_refuses_unmet_dependency_without_writing_sidecar(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Dependency", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    revision = canonical_plan_revision("epic_002", root=root)
    assert revision is not None

    with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
        sign_off_epic_plan(
            "epic_002",
            "epic_manager",
            revision,
            root=root,
            actor="epic_manager",
        )

    assert read_plan_sign_offs("epic_002", root=root) == ()
    readiness = compute_epic_plan_readiness("epic_002", root=root)
    assert readiness is not None
    assert readiness.approve_disabled_reason == "dependency_unmet"


def test_readiness_and_sign_off_observe_dependency_completed_during_planning(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Dependency", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    stale = merged_board(root)
    revision = canonical_plan_revision("epic_002", root=root)
    assert revision is not None
    move_doc("epic_001", "completed", root=root)

    with merged_board_snapshot(root, stale):
        readiness = compute_epic_plan_readiness("epic_002", root=root, board=stale)
        assert readiness is not None
        assert readiness.approve_disabled_reason == "missing_epic_manager_sign_off"
        result = sign_off_epic_plan(
            "epic_002",
            "epic_manager",
            revision,
            root=root,
            actor="epic_manager",
        )

    assert result["newly_signed"] is True
    assert len(read_plan_sign_offs("epic_002", root=root)) == 1


def test_sign_off_writes_no_record_on_dependency_source_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Owner", tier="epic", status="active")
    revision = canonical_plan_revision("epic_001", root=root)
    assert revision is not None
    stale = merged_board(root)

    def fail_refresh(root: Path) -> object:
        raise OSError("source disappeared")

    monkeypatch.setattr(
        "cascade.planning_action_dependencies.refresh_merged_board", fail_refresh
    )
    with merged_board_snapshot(root, stale):
        with pytest.raises(
            DependencyActionRefused, match="dependency_status_unavailable"
        ):
            sign_off_epic_plan(
                "epic_001",
                "epic_manager",
                revision,
                root=root,
                actor="epic_manager",
            )

    assert read_plan_sign_offs("epic_001", root=root) == ()


def test_sign_off_refuses_dependency_regression_hidden_by_request_snapshot(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_001",
        title="Dependency",
        tier="epic",
        status="completed",
    )
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    revision = canonical_plan_revision("epic_002", root=root)
    assert revision is not None
    stale = merged_board(root)
    move_doc("epic_001", "backlog", root=root)

    with merged_board_snapshot(root, stale):
        with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
            sign_off_epic_plan(
                "epic_002",
                "epic_manager",
                revision,
                root=root,
                actor="epic_manager",
            )

    assert read_plan_sign_offs("epic_002", root=root) == ()


def test_feature_approval_fails_closed_after_dependency_regresses(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Dependency",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Owner",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    stale = merged_board(root)
    move_doc("feat_001", "backlog", root=root)

    with merged_board_snapshot(root, stale):
        with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
            approve_feature("feat_002", root=root)

    assert read_doc("feat_002", root=root).meta.approved_at is None


def test_source_refresh_failure_refuses_without_feature_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")

    def fail_refresh(root: Path) -> object:
        raise OSError("source disappeared")

    monkeypatch.setattr(
        "cascade.planning_action_dependencies.refresh_merged_board", fail_refresh
    )
    with pytest.raises(
        DependencyActionRefused, match="dependency_status_unavailable"
    ):
        approve_feature("feat_001", root=root)

    assert read_doc("feat_001", root=root).meta.approved_at is None


def test_epic_approval_checks_only_epic_dependencies_before_bulk_write(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_001",
        title="Prerequisite",
        tier="epic",
        status="completed",
    )
    add_doc(
        root,
        id="epic_002",
        title="Epic",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    add_doc(root, id="feat_002_001", title="First", tier="feature", parent="epic_002")
    add_doc(
        root,
        id="feat_002_002",
        title="Second",
        tier="feature",
        parent="epic_002",
        depends_on=["feat_002_001"],
    )
    sign_off_both_planning_roles("epic_002", root=root)

    result = approve_epic_plan("epic_002", root=root)

    assert result["features"] == ["feat_002_001", "feat_002_002"]
    assert read_doc("feat_002_001", root=root).meta.approved_at is not None
    assert read_doc("feat_002_002", root=root).meta.approved_at is not None


def test_epic_dependency_regression_refuses_before_any_bulk_approval(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_001",
        title="Prerequisite",
        tier="epic",
        status="completed",
    )
    add_doc(
        root,
        id="epic_002",
        title="Epic",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    add_doc(root, id="feat_002_001", title="First", tier="feature", parent="epic_002")
    add_doc(root, id="feat_002_002", title="Second", tier="feature", parent="epic_002")
    sign_off_both_planning_roles("epic_002", root=root)
    approve_feature("feat_002_001", root=root)
    existing_approval = read_doc("feat_002_001", root=root).meta.approved_at
    assert existing_approval is not None
    move_doc("epic_001", "backlog", root=root)

    with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
        approve_epic_plan("epic_002", root=root)

    assert read_doc("feat_002_001", root=root).meta.approved_at == existing_approval
    assert read_doc("feat_002_002", root=root).meta.approved_at is None
    assert read_doc("epic_002", root=root).meta.plan_approved_at is None


def test_approval_routes_expose_dependency_refusal_code(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Prerequisite", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Epic",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        parent="epic_002",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_002",
        depends_on=["feat_001"],
    )
    handler = _ApprovalHandler(root)

    WarRoomRequestHandler._handle_approve_feature(handler, {"id": "feat_002"})  # type: ignore[arg-type]
    WarRoomRequestHandler._handle_approve_epic_plan(handler, {"id": "epic_002"})  # type: ignore[arg-type]

    assert handler.responses == [
        (
            HTTPStatus.CONFLICT,
            {
                "ok": False,
                "code": "dependency_unmet",
                "error": "dependency_unmet",
            },
        ),
        (
            HTTPStatus.CONFLICT,
            {
                "ok": False,
                "code": "dependency_unmet",
                "error": "dependency_unmet",
            },
        ),
    ]
    assert read_doc("feat_001", root=root).meta.approved_at is None
    assert read_doc("feat_002", root=root).meta.approved_at is None
    assert read_doc("epic_002", root=root).meta.plan_approved_at is None


def test_mint_allows_incomplete_child_predecessor_when_owner_is_ready(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")

    minted = mint_feature(
        "Second",
        depends_on=["feat_001"],
        epic_id="epic_001",
        root=root,
    )

    assert read_doc(minted, root=root).meta.depends_on == ["feat_001"]


def test_sequential_mint_bulk_approval_and_dependency_gated_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.watchdog.dispatch.has_git", lambda _root: False)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)

    first = mint_feature("First", epic_id="epic_001", root=root)
    second = mint_feature(
        "Second", depends_on=[first], epic_id="epic_001", root=root
    )
    third = mint_feature(
        "Third", depends_on=[second], epic_id="epic_001", root=root
    )
    sign_off_both_planning_roles("epic_001", root=root)

    approved = approve_epic_plan("epic_001", root=root)

    assert approved["features"] == [first, second, third]
    assert all(
        read_doc(feature_id, root=root).meta.approved_at is not None
        for feature_id in (first, second, third)
    )
    assert dispatch_feature(second, "boss", root=root).reason == "dependency_unmet"
    assert dispatch_feature(first, "boss", root=root).ok

    move_doc(first, "completed", root=root)
    assert dispatch_feature(second, "boss", root=root).ok
    assert dispatch_feature(third, "boss", root=root).reason == "dependency_unmet"

    move_doc(second, "completed", root=root)
    assert dispatch_feature(third, "boss", root=root).ok


def test_mint_refreshes_owner_after_cached_dependency_regresses(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Prerequisite", tier="epic", status="completed")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    stale = merged_board(root)
    move_doc("epic_001", "backlog", root=root)

    with merged_board_snapshot(root, stale):
        with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
            mint_feature("Must not exist", epic_id="epic_002", root=root)

    assert set(list_board(root).by_id) == {"epic_001", "epic_002"}
    assert read_doc("epic_002", root=root).meta.children == []


def test_mint_refreshes_owner_after_dependency_completes(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Prerequisite", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    stale = merged_board(root)
    move_doc("epic_001", "completed", root=root)

    with merged_board_snapshot(root, stale):
        minted = mint_feature("Freshly authorized", epic_id="epic_002", root=root)

    assert read_doc(minted, root=root).meta.parent == "epic_002"


def test_mint_refresh_failure_leaves_no_child_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Owner", tier="epic", status="active")

    def fail_refresh(root: Path) -> object:
        raise OSError("source unavailable")

    monkeypatch.setattr(
        "cascade.planning_action_dependencies.refresh_merged_board", fail_refresh
    )
    with pytest.raises(
        DependencyActionRefused, match="dependency_status_unavailable"
    ):
        mint_feature("Must not exist", epic_id="epic_001", root=root)

    assert set(list_board(root).by_id) == {"epic_001"}
    assert read_doc("epic_001", root=root).meta.children == []
