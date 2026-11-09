from __future__ import annotations

from pathlib import Path
import time
from datetime import datetime, timezone
import subprocess

import pytest

from cascade.board.context import set_project_context
from cascade.board.store import read_doc
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.epic.recovery import (
    reconcile_completion_rollup,
    restore_feature_dispatch,
)
from cascade.epic.registry import epic_tools
from cascade.epic.wiring import load_epic_tools
from cascade.watchdog.audit import project_audit_observation
from cascade.workspace.integration_worktree import (
    create_integration_worktree,
    doc_filesystem_root,
)
from cascade.workspace.kickoff import wait_for_background_kickoffs
from tests.support import (
    add_doc,
    make_repo,
)


@pytest.fixture(autouse=True)
def _reset_project_context() -> None:
    set_project_context(None)


@pytest.fixture(autouse=True)
def _supported_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    now = time.time()
    inventory = ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="Offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, now, now + 300, 300),
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr(
        "cascade.watchdog.dispatch._provider_preflight_refusal",
        lambda *_args, **_kwargs: None,
    )
    yield
    wait_for_background_kickoffs(5)
    set_project_context(None)


def _dispatchable_epic(root: Path) -> None:
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="ready_to_plan",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "planning board"], cwd=root, check=True)
    entry = create_integration_worktree(
        "epic",
        "epic_001",
        branch="epic/epic_001",
        base_ref="main",
        trunk=root,
    )
    from cascade.board.store import move_doc

    move_doc("epic_001", "active", root=entry.path)

    from cascade.board.store import write_doc

    epic_root = doc_filesystem_root("epic_001", trunk=root)
    epic = read_doc("epic_001", root=epic_root)
    epic.meta.plan_approved_at = datetime.now(timezone.utc)
    write_doc(epic, root=epic_root)
    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = datetime.now(timezone.utc)
    write_doc(feature, root=root)


def test_registered_epic_adapter_dispatches_exact_direct_feature_once(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, role_skills=True)
    _dispatchable_epic(root)
    observation = project_audit_observation("epic_001", root=root)
    action = observation.evidence.parent_action
    assert action is not None
    assert action.candidate_action == "restore_child_dispatch:feat_001"

    load_epic_tools()
    adapter = epic_tools()["restore_feature_dispatch"]
    result = adapter(
        "feat_001",
        epic_id="epic_001",
        root=root,
        expected_generation=str(observation.generation),
    )

    assert result["ok"] is True, result
    assert result["outcome"] == "pending_feature_result"
    assert result["durable_result"] is False
    feature_root = doc_filesystem_root("feat_001", trunk=root)
    assert read_doc("feat_001", root=feature_root).meta.status == "active"


def test_epic_adapter_refuses_changed_generation_and_preserves_gate(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, role_skills=True)
    _dispatchable_epic(root)
    observation = project_audit_observation("epic_001", root=root)

    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = None
    from cascade.board.store import write_doc

    write_doc(feature, root=root)

    with pytest.raises(RuntimeError, match="generation changed"):
        restore_feature_dispatch(
            "feat_001",
            epic_id="epic_001",
            root=root,
            expected_generation=str(observation.generation),
        )
    assert read_doc("feat_001", root=root).meta.status == "backlog"


def test_epic_completion_adapter_reconciles_terminal_result_once(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, role_skills=True)
    _dispatchable_epic(root)
    epic_root = doc_filesystem_root("epic_001", trunk=root)
    from cascade.board.store import move_doc

    move_doc("feat_001", "completed", root=epic_root)
    observation = project_audit_observation("epic_001", root=root)
    action = observation.evidence.parent_action
    assert action is not None
    assert action.candidate_action == "reconcile_completion_rollup"

    first = reconcile_completion_rollup(
        epic_id="epic_001",
        root=root,
        expected_generation=str(observation.generation),
    )
    second = reconcile_completion_rollup(epic_id="epic_001", root=root)

    assert first["outcome"] == "completed"
    assert first["durable_result"] is True
    assert second["outcome"] == "completed"
    assert second["durable_result"] is True
    from cascade.watchdog.events import read_events

    events, _ = read_events("war_room", 0, root=root)
    assert len(
        [
            event
            for event in events
            if event.type == "EpicCompleted"
            and event.payload.get("epic_id") == "epic_001"
        ]
    ) == 1
