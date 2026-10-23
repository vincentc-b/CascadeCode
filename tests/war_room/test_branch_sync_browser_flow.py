"""Branch sync update action and recovery UI browser flow (task_016_002_002)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest

from cascade.task.worktree import create_task_worktree
from cascade.workspace.integration_worktree import integration_branch, integration_worktree_path
from tests.war_room.test_branch_sync_api import (
    _active_stack,
    _commit_on_branch,
    _free_port,
    _initial_commit,
)

_DIR = Path(__file__).resolve().parent
_BROWSER_FLOW = _DIR / "branch_sync_browser_flow.mjs"


def _find_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    for candidate in ("/usr/bin/node", "/usr/local/bin/node"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _run_browser_phase(env: dict[str, str]) -> None:
    node = _find_node()
    if not node:
        pytest.skip("node not on PATH")
    result = subprocess.run(
        [node, str(_BROWSER_FLOW)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def _war_room_includes_branch_sync_script(base: str) -> None:
    with urllib.request.urlopen(f"{base}/") as resp:
        html = resp.read().decode()
    assert "/static/branch_sync_ui.js" in html
    assert html.index("/static/branch_sync_ui.js") < html.index("/static/war_room.js")


@pytest.fixture
def branch_sync_ui_server(tmp_path, monkeypatch):
    from cascade.task.worktree import clear_task_runs
    from cascade.war_room.server import serve
    from tests.support import make_repo

    clear_task_runs()
    root = make_repo(tmp_path, parallelism=4)
    _initial_commit(root)
    _active_stack(root)
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_on_branch(epic_wt, "epic/epic_001", "epic.txt", "epic work\n", "on epic")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root, monkeypatch
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        clear_task_runs()


def test_branch_sync_lifecycle_browser_flow(branch_sync_ui_server) -> None:
    base, root, monkeypatch = branch_sync_ui_server
    _war_room_includes_branch_sync_script(base)

    _run_browser_phase(
        {
            "BRANCH_SYNC_FLOW_PHASE": "behind",
            "WAR_ROOM_BASE": base,
            "WORK_ID": "feat_001",
        }
    )

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    dirty = feat_wt / "staged.txt"
    dirty.write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=feat_wt, check=True, capture_output=True)

    _run_browser_phase(
        {
            "BRANCH_SYNC_FLOW_PHASE": "disabled",
            "WAR_ROOM_BASE": base,
            "WORK_ID": "feat_001",
        }
    )

    subprocess.run(["git", "reset", "HEAD", "staged.txt"], cwd=feat_wt, check=True, capture_output=True)
    dirty.unlink()

    _run_browser_phase(
        {
            "BRANCH_SYNC_FLOW_PHASE": "update_success",
            "WAR_ROOM_BASE": base,
            "WORK_ID": "feat_001",
        }
    )

    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_on_branch(epic_wt, "epic/epic_001", "conflict.txt", "base side\n", "epic change")
    _commit_on_branch(feat_wt, "feat/feat_001", "conflict.txt", "work side\n", "feature change")

    _run_browser_phase(
        {
            "BRANCH_SYNC_FLOW_PHASE": "conflict",
            "WAR_ROOM_BASE": base,
            "WORK_ID": "feat_001",
        }
    )

    create_task_worktree(
        "task_001",
        root=root,
        parent_rev=None,
        skills=[],
        base_ref=integration_branch("feature", "feat_001"),
    )

    _run_browser_phase(
        {
            "BRANCH_SYNC_FLOW_PHASE": "retry_actions",
            "WAR_ROOM_BASE": base,
            "WORK_ID": "task_001",
        }
    )


def test_branch_sync_browser_flow_busy_disabled(branch_sync_ui_server) -> None:
    base, root, monkeypatch = branch_sync_ui_server
    monkeypatch.setattr(
        "cascade.workspace.branch_synchronization._graph_has_inflight_turn",
        lambda *_a, **_k: True,
    )
    _run_browser_phase(
        {
            "BRANCH_SYNC_FLOW_PHASE": "disabled",
            "WAR_ROOM_BASE": base,
            "WORK_ID": "feat_001",
        }
    )
