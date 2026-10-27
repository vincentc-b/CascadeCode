from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.feature.recovery import recovery_status, revise_task, retry_task
from cascade.task.execution import mark_terminal
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from tests.support import add_doc, make_repo, approve_board_feature


def _board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    from cascade.board.store import write_doc

    write_doc(task, root=task.meta.path.parents[3])
    return root


def test_feature_team_can_revise_and_retry_its_blocked_child(tmp_path: Path) -> None:
    root = _board(tmp_path)
    original = read_doc("task_001", root=root).body
    revised = original.replace(
        "## Implementation notes\n\nNotes for the implementer.",
        "## Implementation notes\n\nProduces code and tests.",
    )

    assert revise_task("task_001", revised, feature_id="feat_001", root=root)
    assert "Produces code" in read_doc("task_001", root=root).body
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"] is True
    assert read_doc("task_001", root=root).meta.status == "active"


def test_feature_team_cannot_revise_foreign_task(tmp_path: Path) -> None:
    root = _board(tmp_path)
    with pytest.raises(NotFound):
        revise_task("task_001", "# no", feature_id="feat_999", root=root)


def test_recovery_status_marks_transient_forge_failure_retryable(tmp_path: Path) -> None:
    root = _board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="forge connection timeout")

    status = recovery_status("task_001", feature_id="feat_001", root=root)

    assert status["phase"] == "terminal"
    assert status["reason"] == "transient_forge_failure"
    assert status["attempt_count"] >= 1
    assert status["affected"]["branch"] == "task/task_001"
    assert status["terminal_blocker"] == {"retryable": True}
    assert status["action"] == "retry"
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"] is True


def test_permission_refusal_is_not_retryable_or_a_permission_bypass(tmp_path: Path) -> None:
    root = _board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="permission denied by forge")

    status = recovery_status("task_001", feature_id="feat_001", root=root)
    result = retry_task("task_001", feature_id="feat_001", root=root)

    assert status["reason"] == "permission_refused"
    assert status["terminal_blocker"] == {"retryable": False}
    assert status["action"] == "permission"
    assert result["ok"] is False
    assert result["reason"] == "not_retryable"
    assert read_doc("task_001", root=root).meta.status == "blocked"


def test_concurrent_retry_requests_resume_at_most_one_execution(tmp_path: Path) -> None:
    root = _board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="forge unavailable")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _unused: retry_task("task_001", feature_id="feat_001", root=root),
            range(4),
        ))

    assert sum(result["ok"] is True for result in results) == 1
    assert read_doc("task_001", root=root).meta.status == "active"
