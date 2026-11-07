"""Provider capability gates at the lifecycle dispatch boundaries."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.epic.checkpoint import checkpoint_path
from cascade.board.store import read_doc, write_doc
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task, read_events
from cascade.workspace.integration_worktree import get_integration_worktree
from tests.support import add_doc, approve_board_feature, commit_board, make_repo


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


def _unavailable_inventory() -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(),
        failures=(
            ProviderInventoryFailure(
                provider_id="codex",
                reason="not_authenticated",
                message="sign in required",
            ),
        ),
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
    assert tuple(item.role for item in result.preflight.checks) == (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert read_doc("epic_001", root=root).meta.status == "ready_to_plan"


def test_epic_activation_checks_future_feature_and_swe_roles_before_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    for role in ("epic_manager", "epic_architect"):
        _pin_model(root, "epic_001", role, "offered")
    for role in ("feature_lead", "feature_architect", "swe"):
        _pin_model(root, "epic_001", role, "future-model")
    commit_board(root)
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)

    result = activate_epic("epic_001", "human", root=root)

    assert result.reason == "provider_preflight_blocked"
    assert result.preflight is not None
    assert result.preflight.affected_roles == (
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert read_doc("epic_001", root=root).meta.status == "ready_to_plan"
    assert get_integration_worktree(root, "epic", "epic_001") is None
    assert not checkpoint_path("epic_001", root=root).exists()
    events, _ = read_events("epic_001", 0, root=root)
    assert events == []


def test_failed_epic_preflight_creates_no_worktree_checkpoint_or_event(
    tmp_path: Path, monkeypatch
) -> None:
    """The first durable activation action remains after provider preflight."""

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    for role in ("epic_manager", "epic_architect"):
        _pin_model(root, "epic_001", role, "missing")
    commit_board(root)
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)

    result = activate_epic("epic_001", "human", root=root)

    assert result.reason == "provider_preflight_blocked"
    assert read_doc("epic_001", root=root).meta.status == "ready_to_plan"
    assert get_integration_worktree(root, "epic", "epic_001") is None
    assert not checkpoint_path("epic_001", root=root).exists()
    events, _ = read_events("epic_001", 0, root=root)
    assert events == []


def test_activation_rejects_stale_owning_document_before_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    for role in (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    ):
        _pin_model(root, "epic_001", role, "offered")
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.parse_doc",
        lambda _path: (_ for _ in ()).throw(OSError("unsafe raw detail")),
    )

    result = activate_epic("epic_001", "human", root=root)

    assert result.reason == "provider_preflight_blocked"
    assert result.preflight is not None
    assert result.preflight.action == "epic_activation"
    assert result.preflight.reason_code == "stale_selection"
    assert result.preflight.affected_roles == (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert "unsafe raw detail" not in result.preflight.message
    assert read_doc("epic_001", root=root).meta.status == "ready_to_plan"
    events, _ = read_events("epic_001", 0, root=root)
    assert events == []


def test_transient_preflight_preserves_state_and_can_be_retried(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    for role in (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    ):
        _pin_model(root, "epic_001", role, "offered")
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", _unavailable_inventory
    )

    unavailable = activate_epic("epic_001", "human", root=root)

    assert unavailable.reason == "provider_preflight_unavailable"
    assert unavailable.preflight is not None
    assert unavailable.preflight.outcome == "transient"
    assert read_doc("epic_001", root=root).meta.status == "ready_to_plan"

    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)
    assert activate_epic("epic_001", "human", root=root).ok


def test_feature_and_task_dispatch_reject_before_transition(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    for role in (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    ):
        _pin_model(root, "epic_001", role, "offered")
    for role in ("feature_lead", "feature_architect", "swe"):
        _pin_model(root, "feat_001", role, "offered")
    _pin_model(root, "task_001", "swe", "offered")
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", _inventory)
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", _inventory)

    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    for role in ("feature_lead", "feature_architect", "swe"):
        _pin_model(root, "feat_001", role, "missing")
    feature = dispatch_feature("feat_001", "human", root=root)

    assert feature.reason == "provider_preflight_blocked"
    assert feature.preflight is not None
    assert feature.preflight.action == "feature_dispatch"
    assert tuple(check.role for check in feature.preflight.checks) == (
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert read_doc("feat_001", root=root).meta.status == "backlog"
    automatic = dispatch_feature("feat_001", "boss", root=root)
    assert automatic.reason == feature.reason
    assert automatic.preflight is not None
    assert automatic.preflight.affected_roles == feature.preflight.affected_roles
    assert (
        automatic.preflight.selection_fingerprint
        == feature.preflight.selection_fingerprint
    )
    assert read_doc("feat_001", root=root).meta.status == "backlog"

    for role in ("feature_lead", "feature_architect", "swe"):
        _pin_model(root, "feat_001", role, "offered")
    assert dispatch_feature("feat_001", "human", root=root).ok
    _pin_model(root, "task_001", "swe", "missing")

    task = dispatch_task("task_001", "human", root=root)

    assert task.reason == "provider_preflight_blocked"
    assert task.preflight is not None
    assert task.preflight.action == "task_dispatch"
    assert task.preflight.checks[0].role == "swe"
    assert read_doc("task_001", root=root).meta.status == "backlog"
    automatic_task = dispatch_task("task_001", "boss", root=root)
    assert automatic_task.reason == task.reason
    assert automatic_task.preflight is not None
    assert automatic_task.preflight.affected_roles == task.preflight.affected_roles
    assert (
        automatic_task.preflight.selection_fingerprint
        == task.preflight.selection_fingerprint
    )
    events, _ = read_events("task_001", 0, root=root)
    assert events == []
