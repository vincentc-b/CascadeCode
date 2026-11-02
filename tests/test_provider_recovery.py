"""Provider recovery validates before touching active-item state."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.discovery.inventory import InventoryFreshness, ProviderInventoryItem, ProviderInventoryResult
from cascade.agent.discovery.types import DiscoveredModel
from cascade.board.store import read_doc
from cascade.provider_recovery import ProviderRecoveryRequest, recover_active_item_provider
from cascade.task.graph import clear_task_graph_sessions, seed_task_role_models
from cascade.watchdog.model_resolve import resolve_backend
from tests.support import add_doc, make_repo


def _inventory(model: str) -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(ProviderInventoryItem("codex", "Codex", (DiscoveredModel(id=model, display_name=model),)),),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 1.0, 1.0),
    )


def _active_task(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path, git=False, models=True)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    task_id = "task_001"
    add_doc(root, id=task_id, title="Task", tier="task", status="active", parent="feat_001")
    task = read_doc(task_id, root=root)
    seed_task_role_models(task_id, swe=resolve_backend("swe", task.meta, root=root), root=root, feature_id="feat_001")
    return root, task_id


def test_invalid_recovery_does_not_mutate_document_or_checkpoint(tmp_path: Path) -> None:
    root, task_id = _active_task(tmp_path)
    before = read_doc(task_id, root=root)
    result = recover_active_item_provider(
        task_id,
        ProviderRecoveryRequest("codex", {"swe": "not-offered"}),
        root=root,
        inventory=_inventory("offered"),
    )
    after = read_doc(task_id, root=root)
    assert result.disposition == "validation_failed"
    assert after.meta.provider == before.meta.provider
    assert after.meta.models == before.meta.models


def test_checkpoint_failure_restores_document_selection(tmp_path: Path, monkeypatch) -> None:
    root, task_id = _active_task(tmp_path)
    before = read_doc(task_id, root=root)

    def fail(*args, **kwargs) -> None:
        raise OSError("checkpoint unavailable")

    monkeypatch.setattr("cascade.provider_recovery._write_pins", fail)
    result = recover_active_item_provider(
        task_id,
        ProviderRecoveryRequest("codex", {"swe": "offered"}),
        root=root,
        inventory=_inventory("offered"),
    )
    after = read_doc(task_id, root=root)
    assert result.disposition == "rolled_back"
    assert after.meta.provider == before.meta.provider
    assert after.meta.models == before.meta.models


def teardown_function() -> None:
    clear_task_graph_sessions()
