"""Execution-boundary provider checks retain one safe blocker per work item."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderCompatibilityEvidence,
    ReasoningCapability,
)
from cascade.agent.execution_preflight import (
    ProviderSelection,
    clear_provider_blocker,
    provider_blocker,
    recheck_provider_capability,
)
from cascade.agent.selection_preflight import evaluate_work_selection
from cascade.board.store import read_doc, write_doc
from tests.support import add_doc, make_repo


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


def _inventory_models(
    *model_ids: str, from_cache: bool = False
) -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=tuple(
                    DiscoveredModel(id=model_id, display_name=model_id)
                    for model_id in model_ids
                ),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(from_cache, 1.0, 2.0, 1.0),
    )


def _task(root: Path, model_id: str) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        parent="feat_001",
    )
    doc = read_doc("task_001", root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {"swe": model_id}
    write_doc(doc, root=root)


def _feature(root: Path) -> tuple[ProviderSelection, ...]:
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    doc = read_doc("feat_001", root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {
        "feature_lead": "offered-model",
        "feature_architect": "missing-model",
        "swe": "missing-model",
    }
    write_doc(doc, root=root)
    return tuple(
        ProviderSelection(role, "codex", model)
        for role, model in doc.meta.models.items()
    )


def test_execution_preflight_upserts_safe_deterministic_blocker_and_clears_it(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _task(root, "missing-model")
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
    assert first.affected_roles == ("swe",)
    assert not second.supported
    blocker = provider_blocker("task_001", root=root)
    assert blocker is not None
    assert blocker["affected_roles"] == ["swe"]
    assert blocker["reason_code"] == "model_not_offered"
    assert blocker["reason"] == "The selected model is not offered"
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


def test_execution_preflight_persists_one_retryable_blocker_across_restart(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _task(root, "offered-model")
    selection = ProviderSelection("swe", "codex", "offered-model")
    unavailable = ProviderInventoryResult(
        providers=(),
        failures=(
            ProviderInventoryFailure(
                provider_id="codex",
                reason="api_error",
                message="provider setup unavailable",
            ),
        ),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: unavailable,
    )

    first = recheck_provider_capability(
        "task_001", tier="task", selections=(selection,), root=root
    )
    second = recheck_provider_capability(
        "task_001", tier="task", selections=(selection,), root=root
    )

    assert not first.supported and first.classification == "transient"
    assert not second.supported and second.classification == "transient"
    # provider_blocker reads the durable JSON anew, the same path a restarted
    # process uses rather than any in-memory incident registry.
    restarted = provider_blocker("task_001", root=root)
    assert restarted is not None
    persisted = json.loads(
        (root / ".cascade" / "provider_blockers.json").read_text(encoding="utf-8")
    )
    assert list(persisted["blockers"]) == ["task_001"]
    assert restarted["work_id"] == "task_001"
    assert restarted["classification"] == "transient"
    assert restarted["reason"] == "Provider discovery is unavailable"
    assert restarted["recommended_remedy"] == "retry_provider_setup"
    assert restarted["affected_roles"] == ["swe"]
    assert "message" not in restarted


def test_blocker_retains_complete_scope_provenance_and_requires_fresh_clear(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    selections = _feature(root)
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory_models("offered-model"),
    )

    blocked = recheck_provider_capability(
        "feat_001", tier="feature", selections=selections, root=root
    )

    assert blocked.affected_roles == ("feature_architect", "swe")
    incident = provider_blocker("feat_001", root=root)
    assert incident is not None
    assert incident["action"] == "execution"
    assert incident["selection_fingerprint"] == blocked.selection_fingerprint
    checks = incident["checks"]
    assert isinstance(checks, list)
    assert [check["role"] for check in checks] == [
        "feature_lead",
        "feature_architect",
        "swe",
    ]
    assert checks[0]["outcome"] == "supported"
    assert checks[1]["document_path"]
    assert checks[1]["document_revision"]
    assert checks[1]["field_sources"]

    # A supported cached result is useful readiness information, but cannot
    # resolve an execution incident.
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory_models("offered-model", "missing-model", from_cache=True),
    )
    cached = recheck_provider_capability(
        "feat_001", tier="feature", selections=selections, root=root
    )
    assert cached.supported
    assert provider_blocker("feat_001", root=root) is not None
    fresh_evidence = replace(
        cached,
        inventory_freshness=replace(cached.inventory_freshness, from_cache=False),
    )
    assert not clear_provider_blocker(
        "feat_001",
        result=replace(fresh_evidence, checks=fresh_evidence.checks[:1]),
        root=root,
    )
    assert not clear_provider_blocker(
        "feat_001",
        result=replace(fresh_evidence, work_id="feat_999"),
        root=root,
    )

    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory_models("offered-model", "missing-model"),
    )
    fresh = recheck_provider_capability(
        "feat_001", tier="feature", selections=selections, root=root
    )
    assert fresh.supported
    assert provider_blocker("feat_001", root=root) is None


def test_post_activation_selection_drift_is_persisted_not_replaced(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _task(root, "reviewed-model")
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory_models("reviewed-model", "stale-runtime-model"),
    )

    result = recheck_provider_capability(
        "task_001",
        tier="task",
        selections=(ProviderSelection("swe", "codex", "stale-runtime-model"),),
        root=root,
    )

    assert result.reason_code == "stale_selection"
    incident = provider_blocker("task_001", root=root)
    assert incident is not None
    assert incident["reason_code"] == "stale_selection"
    check = incident["checks"][0]
    assert check["model_id"] == "reviewed-model"
    assert check["field_sources"]


def test_preview_and_execution_share_effective_selection_and_fingerprint(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _task(root, "offered-model")
    doc = read_doc("task_001", root=root)
    doc.meta.reasoning = {"swe": "high"}
    doc.meta.flex_mode = True
    write_doc(doc, root=root)
    inventory = ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(
                    DiscoveredModel(
                        id="offered-model",
                        display_name="Offered",
                        reasoning=ReasoningCapability("medium", ("high",)),
                        supports_flex_mode=True,
                    ),
                ),
                supports_flex_mode=True,
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: inventory,
    )

    preview = evaluate_work_selection(
        read_doc("task_001", root=root),
        root=root,
        inventory=inventory,
        action="preview",
    ).result
    execution = recheck_provider_capability(
        "task_001",
        tier="task",
        selections=(
            ProviderSelection("swe", "codex", "offered-model", "high", True),
        ),
        root=root,
    )

    assert preview.supported and execution.supported
    assert preview.selection_fingerprint == execution.selection_fingerprint
    preview_check = preview.to_dict()["checks"][0]
    execution_check = execution.to_dict()["checks"][0]
    fields = (
        "role",
        "provider",
        "model_id",
        "reasoning_level",
        "reasoning_effective",
        "reviewed_flex_mode",
        "effective_flex_mode",
        "selection_fingerprint",
    )
    assert {key: preview_check[key] for key in fields} == {
        key: execution_check[key] for key in fields
    }
    # Existing response consumers keep their established batch and flat-check
    # keys while reading the additive shared contract fields above.
    assert {"outcome", "checks", "supported"} <= preview.to_dict().keys()
    assert {
        "outcome",
        "reason",
        "provider",
        "model_id",
        "tier",
        "message",
        "retryable",
    } <= preview_check.keys()


def test_preview_keeps_missing_compatibility_evidence_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _task(root, "offered-model")
    monkeypatch.setattr(
        "cascade.agent.selection_preflight.probe_provider_compatibility",
        lambda _provider: ProviderCompatibilityEvidence(),
    )

    preview = evaluate_work_selection(
        read_doc("task_001", root=root),
        root=root,
        inventory=_inventory(model_id="offered-model"),
        action="preview",
    ).result

    assert preview.outcome == "transient"
    assert preview.reason_code == "capability_unknown"
