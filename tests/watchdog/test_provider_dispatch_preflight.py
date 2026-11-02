"""Provider capability gates at the lifecycle dispatch boundaries."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.board.store import read_doc, write_doc
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from tests.support import add_doc, approve_board_feature, make_repo


def _inventory() -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="Offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def _pin_model(root: Path, work_id: str, role: str, model_id: str) -> None:
    doc = read_doc(work_id, root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {**(doc.meta.models or {}), role: model_id}
    write_doc(doc, root=root)


def test_epic_activation_rejects_unsupported_roles_before_state_change(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    _pin_model(root, "epic_001", "epic_manager", "missing")
    _pin_model(root, "epic_001", "epic_architect", "missing")
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)

    result = activate_epic("epic_001", "human", root=root)

    assert not result.ok
    assert result.reason == "provider_preflight_blocked"
    assert result.preflight is not None
    assert result.preflight.outcome == "blocked"
    assert {item.role for item in result.preflight.checks} == {
        "epic_manager",
        "epic_architect",
    }
    assert read_doc("epic_001", root=root).meta.status == "ready_to_plan"


def test_feature_and_task_dispatch_reject_before_transition(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    for role in ("epic_manager", "epic_architect"):
        _pin_model(root, "epic_001", role, "offered")
    for role in ("feature_lead", "feature_architect"):
        _pin_model(root, "feat_001", role, "missing")
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)

    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    feature = dispatch_feature("feat_001", "human", root=root)

    assert feature.reason == "provider_preflight_blocked"
    assert read_doc("feat_001", root=root).meta.status == "backlog"

    for role in ("feature_lead", "feature_architect"):
        _pin_model(root, "feat_001", role, "offered")
    assert dispatch_feature("feat_001", "human", root=root).ok
    _pin_model(root, "task_001", "swe", "missing")

    task = dispatch_task("task_001", "human", root=root)

    assert task.reason == "provider_preflight_blocked"
    assert task.preflight is not None
    assert task.preflight.checks[0].role == "swe"
    assert read_doc("task_001", root=root).meta.status == "backlog"
