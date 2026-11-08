"""Actual MCP processes preserve target Git and tracking authority boundaries."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from cascade.board.context import get_project_context, set_project_context
from cascade.workspace.types import ProjectContext
from cascade.workspace.integration_worktree import create_integration_worktree
from tests.support import add_doc, make_repo


def _request(name, arguments, index):
    return {
        "jsonrpc": "2.0",
        "id": index,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def _call_server(server, requests):
    result = subprocess.run(
        [server["command"], *server["args"]],
        input="".join(json.dumps(request) + "\n" for request in requests),
        text=True,
        capture_output=True,
        cwd=server["cwd"],
        env={**os.environ, **server["env"]},
        check=True,
        timeout=30,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies) == len(requests), result.stdout + result.stderr
    for reply in replies:
        assert not reply["result"].get("isError"), reply
    return [json.loads(reply["result"]["content"][0]["text"]) for reply in replies]


def test_planning_stdio_restores_split_project_for_owned_manifest_authoring(tmp_path):
    from cascade.agent.mcp_wrappers import build_planning_mcp_servers
    from cascade.agent.planning_sandbox import PlanningSandbox
    from cascade.epic.dependency_manifests import manifest_path
    from tests.epic.test_dependency_manifest_authoring import manifest

    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="active")
    owned = create_integration_worktree(
        "epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=tracking
    )
    set_project_context(ProjectContext.split(target, tracking))
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sandbox = PlanningSandbox(
        scratch,
        target,
        "epic",
        "epic_001",
        role="epic_architect",
        workspace_dir=owned.path,
    )
    server = next(iter(build_planning_mcp_servers(sandbox).values()))
    config = json.loads(Path(server["env"]["CASCADE_MCP_CONFIG"]).read_text())
    assert config["repo_root"] == str(target)
    assert config["project_context"] == {
        "target_root": str(target),
        "tracking_root": str(tracking),
    }
    results = _call_server(
        server,
        [
            _request(
                "write_dependency_manifest",
                {"manifest": manifest(), "expected_revision": 0},
                1,
            ),
            _request("read_dependency_manifest", {}, 2),
        ],
    )
    assert results[0]["manifest_revision"] == results[1]["manifest_revision"] == 1
    assert manifest_path("epic_001", root=target).is_relative_to(owned.path)
    assert not list(target.rglob("_dependency_manifests/*.json"))


def test_swe_stdio_keeps_source_in_target_and_delivery_state_in_tracking(tmp_path):
    from cascade.task.swe_mcp import build_swe_mcp_servers
    from cascade.task.execution import mark_queued, execution_view
    from cascade.task_rollup import pending_task_merges
    from cascade.task.action_recovery import load_action

    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    (target / "feature.txt").write_text("base\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=target, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Target source"],
        cwd=target,
        check=True,
        capture_output=True,
    )
    add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        tracking,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        tracking,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    feature = create_integration_worktree(
        "feature", "feat_001", branch="feat/feat_001", base_ref="HEAD", trunk=target
    )
    task = create_integration_worktree(
        "task",
        "task_001",
        branch="task/task_001",
        base_ref=feature.branch,
        trunk=target,
    )
    set_project_context(ProjectContext.split(target, tracking))
    mark_queued("task_001", root=target)
    server = next(iter(build_swe_mcp_servers("task_001", root=target).values()))
    config = json.loads(Path(server["env"]["CASCADE_TASK_MCP_CONFIG"]).read_text())
    assert config["repo_root"] == str(target)
    assert config["project_context"]["tracking_root"] == str(tracking)
    replies = _call_server(
        server,
        [
            _request(
                "swe_write",
                {"path": ".gitignore", "content": "__pycache__/\n.pytest_cache/\n"},
                1,
            ),
            _request(
                "swe_write",
                {
                    "path": "test_delivery.py",
                    "content": "from pathlib import Path\ndef test_source():\n    assert Path('feature.txt').read_text() == 'base\\n'\n",
                },
                2,
            ),
            _request("swe_commit", {"message": "Validate target source"}, 3),
            _request(
                "swe_run_tests",
                {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                4,
            ),
        ],
    )
    assert replies[-1]["exit_code"] == 0
    assert (task.path / "test_delivery.py").is_file()
    assert not (tracking / "test_delivery.py").exists()
    assert execution_view("task_001", root=tracking)["phase"] == "awaiting_merge"
    assert pending_task_merges(target) == pending_task_merges(tracking) == {"task_001"}
    assert (
        load_action("task_001:queued_merge", root=tracking)["metadata"][
            "final_validation"
        ]
        == replies[-1]["final_validation"]
    )
    assert not (target / ".cascade/executions.json").exists()
    assert not (task.path / ".cascade/executions.json").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"target_root": "relative", "tracking_root": "/tmp/tracking"},
        {"target_root": "/tmp", "tracking_root": "/tmp", "extra": True},
    ],
)
def test_project_context_config_rejects_malformed_mapping(payload):
    from cascade.agent.mcp_project_context import restore_project_context

    with pytest.raises(ValueError):
        restore_project_context(payload)


def test_legacy_config_clears_project_context():
    from cascade.agent.mcp_project_context import restore_project_context

    set_project_context(
        ProjectContext.split(Path("/tmp/source"), Path("/tmp/tracking"))
    )
    restore_project_context(None)
    assert get_project_context() is None
