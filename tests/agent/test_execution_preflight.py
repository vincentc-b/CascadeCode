"""Execution-boundary provider checks retain one safe blocker per work item."""

from __future__ import annotations

import json
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
