"""Focused coverage for provenance-aware direct-report propagation."""

from pathlib import Path

from cascade.board.store import read_doc
from cascade.watchdog.blockage import propagate_direct_report_blockage
from tests.support import add_doc, make_repo


def _pair(tmp_path: Path, *, supervisor_status: str = "active"):
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    supervisor = add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status=supervisor_status,
        parent="epic_001",
        children=["task_001"],
    )
    child = add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="blocked",
        parent="feat_001",
    )
    return root, supervisor, child


def test_propagates_with_machine_readable_provenance(tmp_path: Path) -> None:
    root, supervisor, child = _pair(tmp_path)

    result = propagate_direct_report_blockage(
        supervisor, child, "  recovery   refused  ", root=root
    )

    assert result.outcome == "applied"
    persisted = read_doc("feat_001", root=root)
    assert persisted.meta.status == "blocked"
    assert [
        (item.child_id, item.reason, item.blocked_supervisor)
        for item in persisted.meta.monitoring_blockers
    ] == [("task_001", "recovery refused", True)]


def test_equivalent_concurrent_transition_succeeds_but_other_change_conflicts(
    tmp_path: Path,
) -> None:
    root, first_snapshot, child = _pair(tmp_path)
    stale_equivalent = read_doc("feat_001", root=root)
    stale_conflict = read_doc("feat_001", root=root)

    assert propagate_direct_report_blockage(
        first_snapshot, child, "unresolved", root=root
    ).outcome == "applied"
    assert propagate_direct_report_blockage(
        stale_equivalent, child, "unresolved", root=root
    ).outcome == "already_applied"
    assert propagate_direct_report_blockage(
        stale_conflict, child, "different reason", root=root
    ).outcome == "conflict"
    assert len(read_doc("feat_001", root=root).meta.monitoring_blockers) == 1


def test_preexisting_blockage_does_not_give_monitor_ownership(tmp_path: Path) -> None:
    root, supervisor, child = _pair(tmp_path, supervisor_status="blocked")

    result = propagate_direct_report_blockage(supervisor, child, "stuck", root=root)

    assert result.outcome == "applied"
    blocker = read_doc("feat_001", root=root).meta.monitoring_blockers[0]
    assert blocker.blocked_supervisor is False


def test_terminal_supervisor_is_not_mutated(tmp_path: Path) -> None:
    root, supervisor, child = _pair(tmp_path)
    supervisor.meta.status = "completed"
    supervisor.meta.path = (
        root / "docs/features/3_completed" / supervisor.meta.path.name
    )

    result = propagate_direct_report_blockage(supervisor, child, "stuck", root=root)

    assert result.outcome == "terminal"
    assert read_doc("feat_001", root=root).meta.status == "active"
