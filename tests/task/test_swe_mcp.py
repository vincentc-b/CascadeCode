from pathlib import Path

from cascade.task.swe_mcp import build_swe_custom_tools, dispatch_swe_tool
from cascade.task.worktree import clear_task_runs, get_task_run
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from tests.support import add_doc, make_repo, approve_board_feature


def test_out_of_process_tool_restores_active_task_run(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok

    clear_task_runs()
    dispatch_swe_tool(
        "swe_write",
        {"path": "delivery.txt", "content": "implemented\n"},
        task_id="task_001",
        repo_root=root,
        tool_names=["swe_write"],
    )

    run = get_task_run("task_001")
    assert run is not None
    assert (run.worktree / "delivery.txt").read_text(encoding="utf-8") == "implemented\n"


def test_cursor_custom_tool_writes_through_guarded_dispatch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok

    tools = build_swe_custom_tools("task_001", root=root)
    tools["swe_write"].execute(
        {"path": "delivery.txt", "content": "implemented\n"}, None
    )

    run = get_task_run("task_001")
    assert run is not None
    assert (run.worktree / "delivery.txt").read_text(encoding="utf-8") == "implemented\n"
