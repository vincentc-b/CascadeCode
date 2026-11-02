"""Execution-boundary provider checks retain one safe blocker per work item."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.agent.execution_preflight import (
    ProviderSelection,
    provider_blocker,
    recheck_provider_capability,
)
from tests.support import make_repo


def _inventory(*, model_id: str) -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id=model_id, display_name=model_id),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def test_execution_preflight_upserts_safe_deterministic_blocker_and_clears_it(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    selection = ProviderSelection("swe", "codex", "missing-model")
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory(model_id="offered-model"),
    )

    first = recheck_provider_capability(
        "task_001", tier="task", selections=(selection,), root=root
    )
    second = recheck_provider_capability(
        "task_001", tier="task", selections=(selection,), root=root
    )

    assert not first.supported and first.classification == "deterministic"
    assert not second.supported
    blocker = provider_blocker("task_001", root=root)
    assert blocker is not None
    assert blocker["affected_roles"] == ["swe"]
    assert blocker["reason_code"] == "model_not_offered"
    assert blocker["recommended_remedy"] == "choose_provider_or_model"
    assert "message" not in blocker

    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory(model_id="missing-model"),
    )
    supported = recheck_provider_capability(
        "task_001", tier="task", selections=(selection,), root=root
    )
    assert supported.supported
    assert provider_blocker("task_001", root=root) is None
