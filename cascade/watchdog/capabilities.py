"""Incident-scoped executable authority for the health auditor.

The registry in this module is deliberately narrower than the Feature and Epic
agent tool registries.  A descriptor is admission metadata for an existing
lifecycle operation; it does not create a second implementation or grant the
auditor the rest of an owning team's tools.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from cascade.board.context import resolve_root
from cascade.board.store import read_doc
from cascade.board.types import WorkTier
from cascade.task.action_recovery import (
    create_or_load_action,
    load_action,
    recovery_actions,
    resume_action,
)
from cascade.task.lifecycle_lock import lifecycle_root
from cascade.workspace.integration_worktree import load_registry_readonly

HEALTH_AUDITOR_ROLE = "health_auditor"

OwnerKind = Literal["task_team", "feature_team", "epic_team"]
ProbeState = Literal["available", "missing", "denied"]
DurableStore = Literal[
    "action_recovery", "orphan_delivery", "remediation_dispositions"
]

_GATE_TOKENS = frozenset(
    {
        "approval",
        "comment",
        "dependency",
        "credential",
        "permission",
        "install",
        "destructive_git",
        "force_push",
        "human_gate",
        "ambiguous_conflict",
        "semantic_conflict",
        "owner_decision",
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """Static admission contract for one already-executable operation."""

    name: str
    operation: str
    executor: Callable[..., object] | None
    tiers: frozenset[WorkTier]
    failure_classes: frozenset[str]
    owner_kinds: frozenset[OwnerKind]
    required_evidence: tuple[str, ...]
    durable_store: DurableStore
    attempt_bound: int
    lock_protocol: str
    recheck_protocol: str
    resume_action: str
    action_kind: str | None = None
    requires_action: bool = False
    requires_worktree: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.operation:
            raise ValueError("capability needs a name and operation")
        if self.executor is not None and not callable(self.executor):
            raise ValueError("capability executor must be callable when registered")
        if not self.tiers or not self.failure_classes or not self.owner_kinds:
            raise ValueError("capability scope must be explicit")
        if self.attempt_bound < 1:
            raise ValueError("capability attempt bound must be positive")
        if not self.lock_protocol or not self.recheck_protocol or not self.resume_action:
            raise ValueError("capability recovery protocol must be explicit")
        if self.requires_action and not self.action_kind:
            raise ValueError("an action-backed capability needs an action kind")

    @property
    def allowed_failure_classes(self) -> frozenset[str]:
        return self.failure_classes

    @property
    def allowed_tiers(self) -> frozenset[WorkTier]:
        return self.tiers

    @property
    def durable_result_path(self) -> str:
        name = (
            "executions.json"
            if self.durable_store == "action_recovery"
            else (
                "orphan_delivery_recoveries.json"
                if self.durable_store == "orphan_delivery"
                else "remediation_dispositions.json"
            )
        )
        return f".cascade/{name}"

    @property
    def finite_retry_policy(self) -> Mapping[str, int]:
        return {"attempt_bound": self.attempt_bound}


@dataclass(frozen=True, slots=True)
class CapabilityProbe:
    state: ProbeState
    capability: str
    reason: str
    resume_action: str | None
    role: str = HEALTH_AUDITOR_ROLE
    receipt_action_id: str | None = None

    @property
    def available(self) -> bool:
        return self.state == "available"


class CapabilityRegistry:
    """Small explicit allowlist, independently replaceable in probe tests."""

    def __init__(self, descriptors: tuple[CapabilityDescriptor, ...] = ()) -> None:
        self._descriptors = {descriptor.name: descriptor for descriptor in descriptors}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        self._descriptors[descriptor.name] = descriptor

    def unregister(self, name: str) -> None:
        self._descriptors.pop(name, None)

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._descriptors.values())

    def resolve(
        self,
        operation: str,
        *,
        tier: WorkTier,
        owner_kind: OwnerKind,
    ) -> CapabilityDescriptor | None:
        direct = self._descriptors.get(operation)
        candidates = (
            (direct,) if direct is not None else tuple(
                row
                for row in self._descriptors.values()
                if row.operation == operation or row.action_kind == operation
            )
        )
        return next(
            (
                row
                for row in candidates
                if tier in row.tiers and owner_kind in row.owner_kinds
            ),
            None,
        )

    def fingerprint(self) -> str:
        payload = [
            {
                "name": row.name,
                "operation": row.operation,
                "tiers": sorted(row.tiers),
                "failures": sorted(row.failure_classes),
                "owners": sorted(row.owner_kinds),
                "evidence": list(row.required_evidence),
                "store": row.durable_store,
                "attempt_bound": row.attempt_bound,
                "action_kind": row.action_kind,
                "requires_action": row.requires_action,
                "requires_worktree": row.requires_worktree,
                "lock_protocol": row.lock_protocol,
                "recheck_protocol": row.recheck_protocol,
                "resume_action": row.resume_action,
                "registered": callable(row.executor),
            }
            for row in sorted(self._descriptors.values(), key=lambda item: item.name)
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def default_capability_registry() -> CapabilityRegistry:
    """Bind the allowlist to production lifecycle callables.

    Loading the owner tool registries only performs in-process registration.
    No graph, model, forge, Git, or lifecycle operation is invoked here.
    """

    from cascade.epic.registry import epic_tools
    from cascade.epic.wiring import load_epic_tools
    from cascade.feature.registry import feature_tools
    from cascade.feature.wiring import load_feature_tools
    from cascade.task.supervisor_recovery import supervisor_recover_task_delivery

    try:
        load_feature_tools()
        feature = feature_tools()
    except Exception:
        feature = {}
    try:
        load_epic_tools()
        epic = epic_tools()
    except Exception:
        epic = {}
    common = {
        "lock_protocol": "owning lifecycle lock in canonical order",
        "recheck_protocol": "reread owner, evidence, and generation before mutation",
    }
    return CapabilityRegistry(
        (
            CapabilityDescriptor(
                name="task.supervisor_recover_task_delivery",
                operation="supervisor_recover_task_delivery",
                executor=supervisor_recover_task_delivery,
                tiers=frozenset({"task"}),
                failure_classes=frozenset(
                    {
                        "orphan_delivery",
                        "stalled_execution",
                        "delivery_reconciliation",
                        "validated_delivery_missing",
                    }
                ),
                owner_kinds=frozenset({"task_team", "feature_team"}),
                required_evidence=("document_revision",),
                durable_store="orphan_delivery",
                attempt_bound=3,
                resume_action=(
                    "Restore the Task lifecycle checkout/queue evidence, then rerun "
                    "probe_capability for this incident."
                ),
                **common,
            ),
            CapabilityDescriptor(
                name="feature.retry_task",
                operation="retry_task",
                executor=feature.get("retry_task"),
                tiers=frozenset({"task"}),
                failure_classes=frozenset({"blocked_task_failed"}),
                owner_kinds=frozenset({"feature_team"}),
                required_evidence=("document_revision",),
                durable_store="remediation_dispositions",
                attempt_bound=3,
                resume_action=(
                    "Restore the direct-child Task recovery evidence, then rerun "
                    "probe_capability for this incident."
                ),
                **common,
            ),
            CapabilityDescriptor(
                name="feature.recover_task",
                operation="recover_task",
                executor=feature.get("recover_task"),
                tiers=frozenset({"task"}),
                failure_classes=frozenset(
                    {"orphan_delivery", "stalled_execution", "delivery_reconciliation"}
                ),
                owner_kinds=frozenset({"feature_team"}),
                required_evidence=("document_revision",),
                durable_store="orphan_delivery",
                attempt_bound=3,
                resume_action=(
                    "Restore the owning Feature registration, then rerun "
                    "probe_capability for this Task incident."
                ),
                **common,
            ),
            CapabilityDescriptor(
                name="feature.retry_integration_branch_update",
                operation="retry_integration_branch_update",
                executor=feature.get("retry_integration_branch_update"),
                tiers=frozenset({"task"}),
                failure_classes=frozenset(
                    {"transient_retry", "integration_branch_update"}
                ),
                owner_kinds=frozenset({"feature_team"}),
                required_evidence=("action_id",),
                durable_store="action_recovery",
                attempt_bound=3,
                action_kind="integration_branch_update",
                requires_action=True,
                requires_worktree=True,
                resume_action=(
                    "Restore the owned Feature worktree and integration action, then "
                    "rerun probe_capability."
                ),
                **common,
            ),
            CapabilityDescriptor(
                name="epic.retry_integration_branch_update",
                operation="retry_integration_branch_update",
                executor=epic.get("retry_integration_branch_update"),
                tiers=frozenset({"feature", "epic"}),
                failure_classes=frozenset(
                    {"transient_retry", "integration_branch_update"}
                ),
                owner_kinds=frozenset({"epic_team"}),
                required_evidence=("action_id",),
                durable_store="action_recovery",
                attempt_bound=3,
                action_kind="integration_branch_update",
                requires_action=True,
                requires_worktree=True,
                resume_action=(
                    "Restore the owned Epic worktree and integration action, then "
                    "rerun probe_capability."
                ),
                **common,
            ),
        )
    )


def startup_capability_probes(
    *, registry: CapabilityRegistry | None = None
) -> tuple[CapabilityProbe, ...]:
    """Prove every startup entry names a callable, bounded durable operation."""

    selected = registry or default_capability_registry()
    probes: list[CapabilityProbe] = []
    for descriptor in selected.descriptors():
        if not callable(descriptor.executor):  # defensive for reconstructed objects
            probes.append(
                CapabilityProbe(
                    "missing",
                    descriptor.name,
                    "operation_not_executable",
                    descriptor.resume_action,
                )
            )
        elif descriptor.durable_store not in {
            "action_recovery",
            "orphan_delivery",
            "remediation_dispositions",
        }:
            probes.append(
                CapabilityProbe(
                    "missing",
                    descriptor.name,
                    "durable_result_path_unregistered",
                    descriptor.resume_action,
                )
            )
        else:
            probes.append(CapabilityProbe("available", descriptor.name, "registered", None))
    return tuple(probes)


def probe_capability(
    incident: Mapping[str, Any],
    concrete_owner: str | Mapping[str, Any],
    *,
    root: Path,
    registry: CapabilityRegistry | None = None,
    persist: bool = True,
) -> CapabilityProbe:
    """Check one incident without invoking its recovery operation.

    The probe verifies registration, exact owner authority, evidence and
    action/worktree reachability, plus the existing durable result path.  Its
    own request/acknowledgement/result receipt is appended to action recovery;
    the selected lifecycle executor is intentionally left for the later locked
    reservation/adapter feature.
    """

    repo = resolve_root(root)
    work_id, tier, failure, operation, evidence, generation = _incident_fields(incident)
    owner_kind, owner_id = _owner_fields(concrete_owner)
    selected = registry or default_capability_registry()
    fallback_resume = (
        f"Register executable operation {operation!r} for {owner_kind}:{owner_id}, "
        "then rerun probe_capability for the same incident generation."
    )
    recorded_owner = incident.get("accountable_owner")
    if recorded_owner is not None and _owner_fields(recorded_owner) != (
        owner_kind,
        owner_id,
    ):
        return CapabilityProbe(
            "denied",
            operation,
            "incident_owner_mismatch",
            "Refresh the incident from canonical ownership before retrying.",
        )
    if not _owner_authorized(work_id, tier, owner_kind, owner_id, repo):
        return CapabilityProbe(
            "denied",
            operation,
            "concrete_owner_not_authorized",
            "Refresh the canonical owner and probe with that exact work ID.",
        )
    descriptor = selected.resolve(operation, tier=tier, owner_kind=owner_kind)
    if descriptor is None:
        return _finish_probe(
            CapabilityProbe("missing", operation, "operation_not_registered", fallback_resume),
            incident=incident,
            owner=(owner_kind, owner_id),
            root=repo,
            registry_fingerprint=selected.fingerprint(),
            attempt_bound=3,
            persist=persist,
        )
    if not callable(descriptor.executor):
        return _missing_probe(
            descriptor,
            "operation_not_executable",
            incident,
            (owner_kind, owner_id),
            repo,
            selected,
            persist,
        )

    denied = _denied_gate(failure, evidence)
    if denied is not None:
        return _finish_probe(
            CapabilityProbe(
                "denied",
                descriptor.name,
                f"protected_gate:{denied}",
                f"The accountable human or owner must resolve the {denied} gate.",
            ),
            incident=incident,
            owner=(owner_kind, owner_id),
            root=repo,
            registry_fingerprint=selected.fingerprint(),
            attempt_bound=descriptor.attempt_bound,
            persist=persist,
        )
    if failure not in descriptor.failure_classes:
        return _finish_probe(
            CapabilityProbe(
                "denied",
                descriptor.name,
                "failure_class_not_allowlisted",
                "Route the incident to its accountable owner; the auditor has no authority.",
            ),
            incident=incident,
            owner=(owner_kind, owner_id),
            root=repo,
            registry_fingerprint=selected.fingerprint(),
            attempt_bound=descriptor.attempt_bound,
            persist=persist,
        )
    missing = next((field for field in descriptor.required_evidence if not evidence.get(field)), None)
    if missing is not None:
        return _missing_probe(
            descriptor,
            f"required_evidence_missing:{missing}",
            incident,
            (owner_kind, owner_id),
            repo,
            selected,
            persist,
        )
    if descriptor.requires_action:
        action_id = str(evidence["action_id"])
        action = load_action(action_id, root=repo)
        if action is None or action.get("action_kind") != descriptor.action_kind:
            return _missing_probe(
                descriptor,
                "required_action_unreachable",
                incident,
                (owner_kind, owner_id),
                repo,
                selected,
                persist,
            )
        action_owner = dict(action.get("recovery") or {}).get("owning_team")
        if action_owner != {"kind": owner_kind, "work_id": owner_id}:
            return _missing_probe(
                descriptor,
                "required_action_owner_mismatch",
                incident,
                (owner_kind, owner_id),
                repo,
                selected,
                persist,
            )
        action_incident = action.get("incident")
        action_work_id = (
            action_incident.get("work_id")
            if isinstance(action_incident, Mapping)
            else None
        )
        if action_work_id is None:
            recovery_evidence = dict(action.get("recovery") or {}).get("evidence")
            if isinstance(recovery_evidence, Mapping):
                action_work_id = recovery_evidence.get("affected_work_id")
        if action_work_id != work_id:
            return _missing_probe(
                descriptor,
                "required_action_work_mismatch",
                incident,
                (owner_kind, owner_id),
                repo,
                selected,
                persist,
            )
    if descriptor.requires_worktree and not _owner_worktree_reachable(
        owner_kind, owner_id, repo
    ):
        return _missing_probe(
            descriptor,
            "required_worktree_unreachable",
            incident,
            (owner_kind, owner_id),
            repo,
            selected,
            persist,
        )
    if not _durable_path_reachable(descriptor.durable_store, repo):
        return _missing_probe(
            descriptor,
            "durable_result_path_unreachable",
            incident,
            (owner_kind, owner_id),
            repo,
            selected,
            persist,
        )
    return _finish_probe(
        CapabilityProbe("available", descriptor.name, "authorized_and_reachable", None),
        incident=incident,
        owner=(owner_kind, owner_id),
        root=repo,
        registry_fingerprint=selected.fingerprint(),
        attempt_bound=descriptor.attempt_bound,
        persist=persist,
    )


def _missing_probe(
    descriptor: CapabilityDescriptor,
    reason: str,
    incident: Mapping[str, Any],
    owner: tuple[OwnerKind, str],
    root: Path,
    registry: CapabilityRegistry,
    persist: bool,
) -> CapabilityProbe:
    return _finish_probe(
        CapabilityProbe("missing", descriptor.name, reason, descriptor.resume_action),
        incident=incident,
        owner=owner,
        root=root,
        registry_fingerprint=registry.fingerprint(),
        attempt_bound=descriptor.attempt_bound,
        persist=persist,
    )


def _finish_probe(
    probe: CapabilityProbe,
    *,
    incident: Mapping[str, Any],
    owner: tuple[OwnerKind, str],
    root: Path,
    registry_fingerprint: str,
    attempt_bound: int,
    persist: bool,
) -> CapabilityProbe:
    if not persist:
        return probe
    work_id, _tier, _failure, operation, evidence, generation = _incident_fields(incident)
    identity = json.dumps(
        {
            "work_id": work_id,
            "generation": generation,
            "operation": operation,
            "registry": registry_fingerprint,
            "state": probe.state,
            "reason": probe.reason,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    action_id = f"{work_id}:health_capability:{digest}"
    owner_kind, owner_id = owner
    details = {
        "affected_work_id": work_id,
        "selected_capability": probe.capability,
        "requested_operation": operation,
        "probe_state": probe.state,
        "reason": probe.reason,
        "resume_action": probe.resume_action,
        "incident_generation": generation,
        "registry_fingerprint": registry_fingerprint,
        "incident_evidence": dict(evidence),
    }
    if probe.state == "denied":
        state, classification = "awaiting_human_gate", "human_gate"
        blocker = {
            "code": probe.reason,
            "message": "The health auditor cannot cross this protected lifecycle gate.",
            "required_action": probe.resume_action or "Resolve the protected gate.",
        }
    elif probe.state == "missing":
        state, classification, blocker = "retryable", "transient_retry", None
    else:
        state, classification, blocker = "ready_to_resume", None, None
    create_or_load_action(
        action_id,
        "health_auditor_capability_probe",
        root=root,
        attempt_bound=attempt_bound,
        recovery_state=state,  # type: ignore[arg-type]
        failure_classification=classification,  # type: ignore[arg-type]
        metadata=details,
        lifecycle_state="capability_probe",
        owning_team={"kind": owner_kind, "work_id": owner_id},
        evidence=details,
        human_blocker=blocker,
    )
    if probe.state == "available":
        _finalize_superseded_missing_receipts(
            current_action_id=action_id,
            work_id=work_id,
            operation=operation,
            root=root,
        )
        resume_action(
            action_id,
            root=root,
            execute=lambda _context: {
                "metadata": {
                    "probe_state": "available",
                    "selected_capability": probe.capability,
                }
            },
        )
    return CapabilityProbe(
        probe.state,
        probe.capability,
        probe.reason,
        probe.resume_action,
        receipt_action_id=action_id,
    )


def _finalize_superseded_missing_receipts(
    *,
    current_action_id: str,
    work_id: str,
    operation: str,
    root: Path,
) -> None:
    """Resolve capability loss across generations for the same concrete owner.

    Installing a capability changes its registry fingerprint and therefore the
    observation generation. Older missing receipts remain historical evidence,
    but must stop blocking once that owner's operation is executable again.
    """

    current = load_action(current_action_id, root=root) or {}
    current_owner = dict(current.get("recovery") or {}).get("owning_team")
    for action in recovery_actions(root=root):
        if action.get("action_id") == current_action_id:
            continue
        metadata = action.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if (
            action.get("action_kind") != "health_auditor_capability_probe"
            or action.get("recovery_state") != "retryable"
            or metadata.get("probe_state") != "missing"
            or metadata.get("affected_work_id") != work_id
            or metadata.get("requested_operation") != operation
            or dict(action.get("recovery") or {}).get("owning_team") != current_owner
        ):
            continue
        prior_action_id = str(action["action_id"])
        resume_action(
            prior_action_id,
            root=root,
            execute=lambda _context: {
                "metadata": {
                    "probe_state": "available",
                    "resolution": "capability_arrived",
                    "superseded_by_action_id": current_action_id,
                }
            },
        )


def _incident_fields(
    incident: Mapping[str, Any],
) -> tuple[str, WorkTier, str, str, Mapping[str, Any], str]:
    if not isinstance(incident, Mapping):
        raise ValueError("capability incident must be a mapping")
    work = incident.get("work") if isinstance(incident.get("work"), Mapping) else {}
    work_id = incident.get("work_id") or work.get("work_id")
    tier = incident.get("tier") or work.get("tier")
    failure = incident.get("failure_class")
    operation = incident.get("selected_capability")
    evidence = incident.get("evidence")
    generation = incident.get("authoritative_generation")
    if not isinstance(work_id, str) or tier not in {"task", "feature", "epic"}:
        raise ValueError("capability incident needs a typed work reference")
    if not isinstance(failure, str) or not isinstance(operation, str):
        raise ValueError("capability incident needs failure class and selected capability")
    if not isinstance(evidence, Mapping) or not isinstance(generation, str):
        raise ValueError("capability incident needs evidence and authoritative generation")
    return work_id, tier, failure, operation, evidence, generation  # type: ignore[return-value]


def _owner_fields(owner: str | Mapping[str, Any]) -> tuple[OwnerKind, str]:
    aliases = {"task": "task_team", "feature": "feature_team", "epic": "epic_team"}
    if isinstance(owner, str):
        kind, separator, work_id = owner.partition(":")
        if not separator:
            raise ValueError("concrete owner must include kind and work ID")
        kind = aliases.get(kind, kind)
    elif isinstance(owner, Mapping):
        kind, work_id = owner.get("kind"), owner.get("work_id")
        kind = aliases.get(str(kind), kind)
    else:
        raise ValueError("concrete owner must be a string or mapping")
    if kind not in {"task_team", "feature_team", "epic_team"} or not isinstance(
        work_id, str
    ):
        raise ValueError("concrete owner is invalid")
    return kind, work_id  # type: ignore[return-value]


def _owner_authorized(
    work_id: str,
    tier: WorkTier,
    owner_kind: OwnerKind,
    owner_id: str,
    root: Path,
) -> bool:
    try:
        doc = read_doc(work_id, root=root)
    except Exception:
        return False
    if doc.meta.tier != tier:
        return False
    if owner_kind == "task_team":
        return tier == "task" and owner_id == work_id
    if owner_kind == "feature_team":
        return (tier == "task" and doc.meta.parent == owner_id) or (
            tier == "feature" and owner_id == work_id
        )
    return (tier == "feature" and doc.meta.parent == owner_id) or (
        tier == "epic" and owner_id == work_id
    )


def _denied_gate(failure: str, evidence: Mapping[str, Any]) -> str | None:
    values: list[str] = [failure]
    for key in ("gate", "gates", "reason", "failure_code", "blocker"):
        value = evidence.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value)
        elif isinstance(value, Mapping):
            values.extend(str(item) for item in value.values())
    conflicts = evidence.get("conflict_paths")
    if isinstance(conflicts, (list, tuple, set)) and conflicts:
        values.append("ambiguous_conflict")
    normalized = " ".join(values).lower().replace("-", "_").replace(" ", "_")
    return next((token for token in sorted(_GATE_TOKENS) if token in normalized), None)


def _owner_worktree_reachable(
    owner_kind: OwnerKind, owner_id: str, root: Path
) -> bool:
    expected = {"task_team": "task", "feature_team": "feature", "epic_team": "epic"}[
        owner_kind
    ]
    return any(
        entry.kind == expected and entry.work_id == owner_id and entry.path.is_dir()
        for entry in load_registry_readonly(root)
    )


def _durable_path_reachable(store: DurableStore, root: Path) -> bool:
    name = {
        "action_recovery": "executions.json",
        "orphan_delivery": "orphan_delivery_recoveries.json",
        "remediation_dispositions": "remediation_dispositions.json",
    }[store]
    path = lifecycle_root(root) / ".cascade" / name
    if path.exists():
        return path.is_file() and os.access(path, os.R_OK | os.W_OK)
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent.is_dir() and os.access(parent, os.W_OK)


__all__ = [
    "HEALTH_AUDITOR_ROLE",
    "CapabilityDescriptor",
    "CapabilityProbe",
    "CapabilityRegistry",
    "default_capability_registry",
    "probe_capability",
    "startup_capability_probes",
]
