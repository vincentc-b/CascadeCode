"""A parent waiting for its child must release the actual delivery boundary."""

from cascade.board.store import read_doc
from cascade.feature.checkpoint import thread_config
from cascade.feature.graph import ensure_feature_graph
from cascade.task import invoke_tool
from cascade.task.action_recovery import load_action
from cascade.task_rollup import retry_pending_task_merges
from cascade.team_supervision import supervise_child
from tests.task.test_delivery_blocker_validation import _delivery
from tests.task.test_delivery_blocker_validation import _isolate_runs as _isolate_runs


def test_real_parent_inspection_explains_yield_then_delivery_converges(tmp_path):
    root, _, _ = _delivery(tmp_path)
    result = invoke_tool(
        "task_001", "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
        root=root, feature_id="feat_001",
    )
    assert result["exit_code"] == 0 and result["final_validation"]
    graph = ensure_feature_graph("feat_001", root=root)
    config = thread_config("feat_001")
    graph.update_state(config, {
        "feature_id": "feat_001",
        "messages": [{"role": "feature_lead", "content": "Inspecting child delivery"}],
    }, as_node="ingest")
    assert retry_pending_task_merges(root) == []
    status = supervise_child("task_001", "inspect", root=root, feature_id="feat_001")
    assert status["phase"] == "awaiting_merge"
    assert status["delivery_wait"] == "parent_turn_boundary"
    assert "Finish this planning turn" in status["next_safe_step"]
    assert status["action"] == "none"
    assert load_action("task_001:queued_merge", root=root)["attempt_count"] == 0
    assert read_doc("task_001", root=root).meta.status == "active"

    graph.update_state(config, {}, as_node="feature_architect")
    assert retry_pending_task_merges(root) == ["task_001"]
    assert read_doc("task_001", root=root).meta.status == "completed"
    assert retry_pending_task_merges(root) == []
