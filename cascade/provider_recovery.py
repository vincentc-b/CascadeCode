"""Atomic provider-selection recovery for active Epic, Feature, and Task work.

This module deliberately does not start a turn.  The lifecycle command owns
quiescence and uses the returned disposition to either resume its checkpoint
or enqueue a new role turn.  Keeping that decision here makes the safety
boundary usable by HTTP and restart recovery alike.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from cascade.agent.discovery.inventory import ProviderInventoryResult, refresh_provider_inventory
from cascade.agent.execution_preflight import ProviderSelection
from cascade.agent.preflight import (
    ProviderCapabilityPreflight,
    RoleCapabilityPreflight,
    batch_provider_capability_preflight,
    preflight_provider_capability,
)
from cascade.board.context import resolve_root
from cascade.board.store import read_doc, write_doc
from cascade.watchdog.lock import process_lock

RecoveryDisposition = Literal["resume_compatible", "fresh_role_turn", "validation_failed", "rolled_back"]

_ROLES = {
    "epic": ("epic_manager", "epic_architect"),
    "feature": ("feature_lead", "feature_architect"),
    "task": ("swe",),
}


@dataclass(frozen=True)
class ProviderRecoveryRequest:
    """A complete replacement selection for every role on the active item."""

    provider: str
    models: Mapping[str, str]
    reasoning: Mapping[str, str | None] | None = None
    flex_mode: bool | None = None


@dataclass(frozen=True)
class ProviderRecoveryResult:
    disposition: RecoveryDisposition
    work_id: str
    affected_roles: tuple[str, ...]
    checks: tuple[RoleCapabilityPreflight, ...]
    mutated: bool
    reason: str

    @property
    def resumable(self) -> bool:
        """Whether it is safe for the caller to resume the existing turn."""

        return self.disposition == "resume_compatible"


def recover_active_item_provider(
    work_id: str,
    request: ProviderRecoveryRequest,
    *,
    root: Path,
    inventory: ProviderInventoryResult | None = None,
) -> ProviderRecoveryResult:
    """Validate then atomically reconcile a work document and checkpoint pins.

    No document or checkpoint is touched until *all* role checks succeed.  If
    either persistence step raises, both visible selections are restored.  A
    checkpoint is resumable only when every opaque provider pin already equals
    the requested selection; changing any pin deliberately asks the lifecycle
    layer to reconstruct a fresh role turn from the preserved graph context.
    """

    repo = resolve_root(root)
    with process_lock:
        doc = read_doc(work_id, root=repo)
        roles = _ROLES[doc.meta.tier]
        checks = _validate_request(doc.meta.tier, roles, request, inventory)
        batch = batch_provider_capability_preflight(checks)
        if not batch.supported:
            return ProviderRecoveryResult(
                "validation_failed", work_id, roles, checks, False, batch.outcome
            )

        before_doc = deepcopy(doc)
        before_pins = _read_pins(work_id, doc.meta.tier, doc.meta.parent, repo)
        compatible = _pins_match(before_pins, roles, request)
        _apply_document_selection(doc, roles, request)
        try:
            # ``write_doc`` is itself atomic at the file boundary.  The
            # compensating write only runs if checkpoint persistence failed.
            write_doc(doc, root=repo)
            _write_pins(work_id, doc.meta.tier, doc.meta.parent, repo, roles, request)
        except Exception:
            try:
                _restore_document(before_doc, repo)
                _restore_pins(work_id, doc.meta.tier, doc.meta.parent, repo, before_pins)
            except Exception:
                # The original exception is more useful to lifecycle callers;
                # best-effort restoration is intentionally contained here.
                pass
            return ProviderRecoveryResult("rolled_back", work_id, roles, checks, False, "persistence_failed")

        return ProviderRecoveryResult(
            "resume_compatible" if compatible else "fresh_role_turn",
            work_id,
            roles,
            checks,
            True,
            "checkpoint_pins_unchanged" if compatible else "checkpoint_pins_replaced",
        )


def _validate_request(
    tier: str,
    roles: tuple[str, ...],
    request: ProviderRecoveryRequest,
    inventory: ProviderInventoryResult | None,
) -> tuple[RoleCapabilityPreflight, ...]:
    available = inventory if inventory is not None else refresh_provider_inventory()
    checks: list[RoleCapabilityPreflight] = []
    for role in roles:
        model = str(request.models.get(role) or "").strip()
        reasoning = request.reasoning.get(role) if request.reasoning else None
        result = preflight_provider_capability(
            provider=request.provider,
            model_id=model,
            tier=tier,
            inventory=available,
            reasoning_level=reasoning.strip() if isinstance(reasoning, str) else None,
            flex_mode=request.flex_mode,
        )
        checks.append(RoleCapabilityPreflight(role, result))
    return tuple(checks)


def _apply_document_selection(doc, roles: tuple[str, ...], request: ProviderRecoveryRequest) -> None:
    doc.meta.provider = request.provider
    # The item owns these role overrides.  Do not walk children or alter their
    # stamped choices; their documents remain untouched by this transaction.
    doc.meta.models = {role: str(request.models[role]).strip() for role in roles}
    reasoning = {
        role: value.strip()
        for role in roles
        if request.reasoning and isinstance((value := request.reasoning.get(role)), str) and value.strip()
    }
    doc.meta.reasoning = reasoning or None
    doc.meta.flex_mode = request.flex_mode


def _graph(work_id: str, tier: str, parent: str | None, root: Path):
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph
        return ensure_epic_graph(work_id, root=root), thread_config(work_id)
    if tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph
        return ensure_feature_graph(work_id, root=root), thread_config(work_id)
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph
    return ensure_task_graph(work_id, root=root, feature_id=parent), thread_config(work_id)


_PIN_KEYS = ("provider_ids", "provider_sources", "model_ids", "model_sources", "reasoning_ids", "reasoning_sources", "flex_modes", "model_id")


def _read_pins(work_id: str, tier: str, parent: str | None, root: Path) -> dict[str, object]:
    graph, config = _graph(work_id, tier, parent, root)
    values = graph.get_state(config).values or {}
    return {key: deepcopy(values.get(key)) for key in _PIN_KEYS}


def _pins_match(pins: Mapping[str, object], roles: tuple[str, ...], request: ProviderRecoveryRequest) -> bool:
    providers = pins.get("provider_ids") or {}
    models = pins.get("model_ids") or {}
    reasoning = pins.get("reasoning_ids") or {}
    flex = pins.get("flex_modes") or {}
    if not all(isinstance(value, Mapping) for value in (providers, models, reasoning, flex)):
        return False
    return all(
        providers.get(role) == request.provider
        and models.get(role) == str(request.models[role]).strip()
        and reasoning.get(role) == (request.reasoning.get(role).strip() if request.reasoning and isinstance(request.reasoning.get(role), str) else None)
        and flex.get(role) == request.flex_mode
        and pins.get("model_id") in (None, "")
        for role in roles
    )


def _write_pins(work_id: str, tier: str, parent: str | None, root: Path, roles: tuple[str, ...], request: ProviderRecoveryRequest) -> None:
    graph, config = _graph(work_id, tier, parent, root)
    current = graph.get_state(config).values or {}
    payload: dict[str, object] = {
        key: dict(current.get(key) or {}) for key in _PIN_KEYS if key != "model_id"
    }
    for role in roles:
        payload["provider_ids"][role] = request.provider
        payload["provider_sources"][role] = "document"
        payload["model_ids"][role] = str(request.models[role]).strip()
        payload["model_sources"][role] = "document-role"
        payload["flex_modes"][role] = request.flex_mode
        reasoning = request.reasoning.get(role) if request.reasoning else None
        if isinstance(reasoning, str) and reasoning.strip():
            payload["reasoning_ids"][role] = reasoning.strip()
            payload["reasoning_sources"][role] = "document-role"
        else:
            payload["reasoning_ids"].pop(role, None)
            payload["reasoning_sources"].pop(role, None)
    # A one-invoke model override is opaque provider-specific state.  Leaving
    # it in place would silently start the next turn on the old model.
    payload["model_id"] = None
    graph.update_state(config, payload)


def _restore_document(doc, root: Path) -> None:
    # Avoid stale-sha rejection while compensating a write made in this process.
    doc.sha = None
    write_doc(doc, root=root)


def _restore_pins(work_id: str, tier: str, parent: str | None, root: Path, pins: Mapping[str, object]) -> None:
    graph, config = _graph(work_id, tier, parent, root)
    graph.update_state(config, dict(pins))


__all__ = ["ProviderRecoveryRequest", "ProviderRecoveryResult", "recover_active_item_provider"]
