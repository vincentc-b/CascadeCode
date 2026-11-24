"""Durable cumulative policy for one original recovery incident.

The budget is an additive collection in the existing action ledger.  This
operation reservations and settlements use the same cross-process lifecycle
transaction as lineage and policy updates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from cascade.board.context import resolve_root
from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.review_owner import current_review_owner, review_owner_exited
from cascade.task.action_recovery import (
    ActionNotFound,
    ActionRecoveryError,
    _actions,
    _copy,
    _read_payload,
    _write_payload,
)
from cascade.task.lifecycle_lock import task_lifecycle_lock, task_lifecycle_read_lock

POLICY_ID = "cascade.recovery.incident-budget"
POLICY_VERSION = 1
_DIMENSIONS = (
    "tool_attempts",
    "paid_turns",
    "process_seconds",
    "model_seconds",
    "elapsed_seconds",
    "known_tokens",
)
DEFAULT_LIMITS = {
    "tool_attempts": 6,
    "paid_turns": 6,
    "process_seconds": 1_800,
    "model_seconds": 1_800,
    "elapsed_seconds": 3_600,
    "known_tokens": 200_000,
}
MAXIMUM_LIMITS = {
    "tool_attempts": 20,
    "paid_turns": 12,
    "process_seconds": 7_200,
    "model_seconds": 7_200,
    "elapsed_seconds": 86_400,
    "known_tokens": 1_000_000,
}
RETRY_POLICY = {
    "deterministic_attempts": 1,
    "transient_attempts": 3,
    "backoff_seconds": [5, 10],
    "jitter_fraction": 0.2,
    "validator_seconds": {"default": 300, "maximum": 3_600},
    "model_turn_seconds": {"default": 300, "maximum": 900},
}


class IncidentBudgetError(ActionRecoveryError):
    """Incident lineage or budget policy cannot be recorded safely."""


class IncidentBudgetAuthorityError(IncidentBudgetError):
    """The caller has no independent authority to extend this incident."""


OperationDecisionState = Literal[
    "admitted", "pending", "exhausted", "owner_decision"
]


@dataclass(frozen=True, slots=True)
class IncidentOperationPermit:
    """A bounded, durable authorization for one expensive operation."""

    incident_id: str
    operation_id: str
    claim_id: str
    policy_version: int
    reserved: Mapping[str, int]
    receipt_id: str


@dataclass(frozen=True, slots=True)
class IncidentOperationDecision:
    """Typed F2/Watchdog admission result; refusals never mint allowance."""

    state: OperationDecisionState
    reason: str
    policy_version: int
    receipt: Mapping[str, Any] | None = None
    permit: IncidentOperationPermit | None = None

    @property
    def admitted(self) -> bool:
        return self.state == "admitted"


def _iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _time(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise IncidentBudgetError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise IncidentBudgetError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise IncidentBudgetError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _authoritative_origin(
    action: Mapping[str, Any],
) -> tuple[str, str, str | None]:
    """Return the earliest trustworthy durable action/attempt timestamp."""

    try:
        candidates = [_time(action.get("created_at"), field="action created_at")]
        attempts = action.get("attempts", [])
        if not isinstance(attempts, list):
            raise IncidentBudgetError("action attempts must be a list")
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, Mapping):
                raise IncidentBudgetError("action attempt history is malformed")
            for name in ("started_at", "claimed_at"):
                if attempt.get(name) is not None:
                    candidates.append(
                        _time(attempt[name], field=f"attempt {index} {name}")
                    )
    except IncidentBudgetError:
        return _iso(None), "unavailable", "legacy_elapsed_origin_ambiguous"
    return min(candidates).isoformat(), "known", None


def _identity(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise IncidentBudgetError(f"{field} must be a nonempty stable string")
    return value


def _generation(value: object) -> str:
    generation = _identity(value, field="generation")
    digest = generation.removeprefix("sha256:")
    if (
        not generation.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise IncidentBudgetError("generation must be a full sha256 identity")
    return generation


def _json_mapping(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IncidentBudgetError(f"{field} must be a mapping")
    try:
        return json.loads(json.dumps(dict(value)))
    except (TypeError, ValueError) as exc:
        raise IncidentBudgetError(f"{field} must be JSON serializable") from exc


def _usage(value: Mapping[str, Any], *, allow_zero: bool, field: str) -> dict[str, int]:
    raw = _json_mapping(value, field=field)
    unknown = set(raw) - set(_DIMENSIONS)
    if unknown:
        raise IncidentBudgetError(f"{field} has unknown dimensions: {sorted(unknown)}")
    result = {dimension: 0 for dimension in _DIMENSIONS}
    for dimension, amount in raw.items():
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise IncidentBudgetError(f"{field}.{dimension} must be an integer")
        if amount < 0 or (not allow_zero and amount == 0):
            qualifier = "nonnegative" if allow_zero else "positive"
            raise IncidentBudgetError(f"{field}.{dimension} must be {qualifier}")
        result[dimension] = amount
    return result


def _complete_usage(value: object, *, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(_DIMENSIONS):
        raise IncidentBudgetError(f"{field} must contain every budget dimension")
    return _usage(value, allow_zero=True, field=field)


def _trusted_policy(value: object) -> tuple[dict[str, int], dict[str, int]]:
    if (
        not isinstance(value, Mapping)
        or value.get("id") != POLICY_ID
        or value.get("version") != POLICY_VERSION
        or value.get("retry") != RETRY_POLICY
    ):
        raise IncidentBudgetError("incident budget has no trusted policy")
    limits = _complete_usage(value.get("limits"), field="policy limits")
    maxima = _complete_usage(value.get("maxima"), field="policy maxima")
    if maxima != MAXIMUM_LIMITS or any(
        limits[dimension] < DEFAULT_LIMITS[dimension]
        or limits[dimension] > maxima[dimension]
        for dimension in _DIMENSIONS
    ):
        raise IncidentBudgetError("incident budget policy is outside trusted bounds")
    return limits, maxima


def _budgets(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    value = payload.get("incident_budgets")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise IncidentBudgetError("incident budget collection is malformed")
    budgets: dict[str, dict[str, Any]] = {}
    for identity, record in value.items():
        if not isinstance(identity, str) or not isinstance(record, Mapping):
            raise IncidentBudgetError("incident budget collection is malformed")
        budgets[identity] = dict(record)
    return budgets


def _action_generation(action: Mapping[str, Any]) -> str:
    incident = action.get("incident")
    if not isinstance(incident, Mapping):
        raise IncidentBudgetError("action has no authoritative incident contract")
    return _generation(incident.get("authoritative_generation"))


def _canonical_parent(action: Mapping[str, Any]) -> str | None:
    candidates: list[object] = []
    for container_name in ("metadata", "recovery"):
        container = action.get(container_name)
        if not isinstance(container, Mapping):
            continue
        candidates.append(container.get("parent_action_id"))
        evidence = container.get("evidence")
        if isinstance(evidence, Mapping):
            candidates.append(evidence.get("parent_action_id"))
    parents = {candidate for candidate in candidates if isinstance(candidate, str)}
    if len(parents) > 1:
        raise IncidentBudgetError("action has ambiguous canonical parent lineage")
    return next(iter(parents), None)


def _legacy_usage(
    action: Mapping[str, Any], evidence: Mapping[str, Any]
) -> tuple[dict[str, int], str, str | None]:
    attempts = action.get("attempts")
    if attempts is None:
        attempts = []
    if not isinstance(attempts, list):
        return (
            _usage({}, allow_zero=True, field="legacy usage"),
            "unavailable",
            "legacy_attempts_malformed",
        )
    # Caller evidence is useful for an owner investigation, but it is not an
    # authenticated accounting source and therefore cannot turn unknown usage
    # into known allowance.  The durable action ledger is the only source this
    # boundary can independently verify.
    if evidence.get("legacy_usage") is not None:
        if not isinstance(evidence["legacy_usage"], Mapping):
            raise IncidentBudgetError("legacy_usage must be a mapping")
        _usage(evidence["legacy_usage"], allow_zero=True, field="legacy usage")
        return (
            _usage({}, allow_zero=True, field="legacy usage"),
            "unavailable",
            "legacy_usage_unverified",
        )
    if attempts:
        return (
            _usage({}, allow_zero=True, field="legacy usage"),
            "unavailable",
            "legacy_usage_unknown",
        )
    return _usage({}, allow_zero=True, field="legacy usage"), "known", None


def _escalation_id(incident_id: str) -> str:
    digest = hashlib.sha256(f"incident-budget:{incident_id}".encode()).hexdigest()
    return f"incident-budget-exhausted:sha256:{digest}"


def _exhaust(record: dict[str, Any], reason: str, stamped: datetime) -> None:
    if record.get("escalation_id") is None:
        record["escalation_id"] = _escalation_id(str(record["incident_id"]))
        record["exhausted_at"] = stamped.isoformat()
        record["exhaustion_reason"] = reason
    record["status"] = "exhausted"
    record["wait_reason"] = "bounded_extension_required"


def _backoff_seconds(operation_id: str, failure_number: int) -> float:
    base = RETRY_POLICY["backoff_seconds"][
        min(failure_number - 1, len(RETRY_POLICY["backoff_seconds"]) - 1)
    ]
    digest = hashlib.sha256(operation_id.encode()).digest()
    unit = int.from_bytes(digest[:2], "big") / 65535
    jitter = (unit * 2 - 1) * RETRY_POLICY["jitter_fraction"]
    return base * (1 + jitter)


def bind_incident_budget(
    incident_id: str,
    action_id: str,
    generation: str,
    evidence: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bind an action generation to one original incident, idempotently.

    A new original identity is anchored to its existing action ID.  A child or
    replacement action must instead cite an action already bound to the same
    incident; caller text alone cannot establish that lineage.
    """

    incident_id = _identity(incident_id, field="incident identity")
    action_id = _identity(action_id, field="action identity")
    generation = _generation(generation)
    facts = _json_mapping(evidence, field="lineage evidence")
    requested_version = facts.get("policy_version", POLICY_VERSION)
    if (
        isinstance(requested_version, bool)
        or not isinstance(requested_version, int)
        or requested_version != POLICY_VERSION
    ):
        raise IncidentBudgetError("untrusted incident budget policy version")
    repo = resolve_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        legacy_lineage_wait = None
        if not isinstance(action.get("incident"), Mapping):
            legacy_lineage_wait = "legacy_lineage_ambiguous"
        elif _action_generation(action) != generation:
            raise IncidentBudgetError("generation does not match the canonical action")

        budgets = _budgets(payload)
        record = budgets.get(incident_id)
        canonical_parent = _canonical_parent(action)
        parent_action_id = facts.get("parent_action_id")
        cited_original = facts.get("original_incident_id")
        bound_budget = action.get("incident_budget_id")
        if bound_budget is not None and bound_budget != incident_id:
            raise IncidentBudgetError("action is already bound to another incident")
        if record is None:
            if incident_id != action_id:
                raise IncidentBudgetError(
                    "a new original incident identity must be anchored to its action"
                )
            if canonical_parent is not None or parent_action_id is not None:
                raise IncidentBudgetError(
                    "a linked action cannot mint a new incident budget"
                )
            charged, quality, wait_reason = _legacy_usage(action, facts)
            admitted_at, origin_quality, origin_wait = _authoritative_origin(action)
            if origin_wait is not None:
                quality = "unavailable"
                wait_reason = origin_wait
            if legacy_lineage_wait is not None:
                quality = "unavailable"
                wait_reason = legacy_lineage_wait
            owner = (
                action.get("recovery", {}).get("owning_team")
                if isinstance(action.get("recovery"), Mapping)
                else None
            )
            record = {
                "schema_version": 1,
                "incident_id": incident_id,
                "original_action_id": action_id,
                "original_admitted_at": admitted_at,
                "original_admission_quality": origin_quality,
                "policy": {
                    "id": POLICY_ID,
                    "version": POLICY_VERSION,
                    "limits": dict(DEFAULT_LIMITS),
                    "maxima": dict(MAXIMUM_LIMITS),
                    "retry": _copy(RETRY_POLICY),
                },
                "accountable_owner": _copy(dict(owner))
                if isinstance(owner, Mapping)
                else None,
                "bindings": [],
                "charged": charged,
                "reserved": _usage({}, allow_zero=True, field="reserved usage"),
                "operations": {},
                "live_claim": None,
                "consumption_quality": quality,
                "extensions": [],
                "escalation_id": None,
                "status": "awaiting_owner_decision" if wait_reason else "active",
                "wait_reason": wait_reason,
            }
            if wait_reason is None and any(
                charged[dimension] >= DEFAULT_LIMITS[dimension]
                for dimension in _DIMENSIONS
            ):
                record.update(
                    escalation_id=_escalation_id(incident_id),
                    exhausted_at=admitted_at,
                    exhaustion_reason="legacy_allowance_exhausted",
                    status="exhausted",
                    wait_reason="bounded_extension_required",
                )
        else:
            if record.get("incident_id") != incident_id:
                raise IncidentBudgetError("incident budget identity is corrupt")
            bound_actions = {
                binding.get("action_id")
                for binding in record.get("bindings", [])
                if isinstance(binding, Mapping)
            }
            if action_id not in bound_actions:
                parent = _identity(parent_action_id, field="parent action identity")
                if canonical_parent is None:
                    raise IncidentBudgetError(
                        "linked action has no canonical parent lineage"
                    )
                if canonical_parent != parent:
                    raise IncidentBudgetError(
                        "lineage evidence disagrees with the action"
                    )
                if cited_original != incident_id or parent not in bound_actions:
                    raise IncidentBudgetError(
                        "linked action needs an already-bound authoritative parent"
                    )
            if legacy_lineage_wait is not None:
                record["status"] = "awaiting_owner_decision"
                record["wait_reason"] = legacy_lineage_wait
                record["consumption_quality"] = "unavailable"

        bindings = list(record.get("bindings") or [])
        matching = [
            item
            for item in bindings
            if isinstance(item, Mapping) and item.get("action_id") == action_id
        ]
        if matching:
            binding = dict(matching[0])
            generations = list(binding.get("generations") or [])
            if legacy_lineage_wait is None and generation not in generations:
                generations.append(generation)
                binding["generations"] = generations
                bindings[bindings.index(matching[0])] = binding
        else:
            bindings.append(
                {
                    "action_id": action_id,
                    "parent_action_id": parent_action_id,
                    "generations": [] if legacy_lineage_wait else [generation],
                    "bound_at": _iso(now),
                    "evidence": facts,
                }
            )
        record["bindings"] = bindings
        action["incident_budget_id"] = incident_id
        if isinstance(action.get("incident"), Mapping):
            incident = dict(action["incident"])
            incident["original_incident_id"] = incident_id
            action["incident"] = incident
        actions[action_id] = action
        budgets[incident_id] = record
        payload["actions"] = actions
        payload["incident_budgets"] = budgets
        payload["version"] = max(int(payload.get("version") or 1), 4)
        _write_payload(repo, payload)
        return _project(record)


def _decision(
    state: OperationDecisionState,
    reason: str,
    *,
    receipt: Mapping[str, Any] | None = None,
    permit: IncidentOperationPermit | None = None,
) -> IncidentOperationDecision:
    return IncidentOperationDecision(
        state, reason, POLICY_VERSION, _copy(dict(receipt)) if receipt else None, permit
    )


def _current_material_is_bound(
    record: Mapping[str, Any], actions: Mapping[str, Mapping[str, Any]]
) -> bool:
    bindings = record.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        return False
    current = False
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise IncidentBudgetError("incident bindings are malformed")
        action_id = binding.get("action_id")
        generations = binding.get("generations")
        if not isinstance(action_id, str) or not isinstance(generations, list):
            raise IncidentBudgetError("incident bindings are malformed")
        action = actions.get(action_id)
        if action is None:
            raise IncidentBudgetError("a bound action is missing")
        if action.get("incident_budget_id") != record.get("incident_id"):
            raise IncidentBudgetError("bound action budget identity is corrupt")
        incident = action.get("incident")
        if not isinstance(incident, Mapping):
            continue
        if incident.get("original_incident_id") != record.get("incident_id"):
            raise IncidentBudgetError("bound action incident identity is corrupt")
        current = current or incident.get("authoritative_generation") in generations
    return current


def _operation_receipt_id(incident_id: str, operation_id: str) -> str:
    digest = hashlib.sha256(
        f"incident-operation:{incident_id}:{operation_id}".encode()
    ).hexdigest()
    return f"sha256:{digest}"


def _review_validator_material(
    record: Mapping[str, Any], actions: Mapping[str, Mapping[str, Any]], operation_id: str
) -> str | None:
    """Bind review checks to admitted inputs, not changing attempts or commit metadata."""
    action_id = record.get("original_action_id")
    action = actions.get(action_id, {})
    if action.get("action_kind") != "review_rebase":
        return None
    generations = action.get("review_publication_generations") or []
    identity = generations[-1].get("identity") if generations else None
    if not isinstance(identity, Mapping):
        return None
    generation_digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not operation_id.startswith(f"review-validator:{action_id}:{generation_digest}:"):
        return None
    keys = (
        "source_tree", "validation_command", "validation_timeout_seconds",
        "budget_policy", "environment_revision",
    )
    if any(identity.get(key) is None for key in keys):
        return None
    material = {key: identity[key] for key in keys}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def reserve_incident_operation(
    incident_id: str,
    operation_id: str,
    kind: str,
    worst_case: Mapping[str, Any],
    claim_id: str,
    policy_version: int,
    *,
    root: Path,
    now: datetime | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> IncidentOperationDecision:
    """Atomically reserve cumulative allowance before an expensive launch."""

    incident_id = _identity(incident_id, field="incident identity")
    operation_id = _identity(operation_id, field="operation identity")
    kind = _identity(kind, field="operation kind")
    claim_id = _identity(claim_id, field="claim identity")
    requested = _usage(worst_case, allow_zero=True, field="worst case")
    launch_attributes = (
        _json_mapping(attributes, field="operation attributes")
        if attributes is not None
        else None
    )
    if not any(requested[dimension] for dimension in _DIMENSIONS if dimension != "elapsed_seconds"):
        raise IncidentBudgetError("an operation must reserve finite allowance")
    if requested["elapsed_seconds"]:
        raise IncidentBudgetError("elapsed_seconds is a deadline, not a reservation")
    if (
        kind.startswith("provider_turn:")
        and requested["model_seconds"] > RETRY_POLICY["model_turn_seconds"]["maximum"]
    ):
        return _decision("owner_decision", "model_runtime_bound_exceeds_policy")
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    repo = resolve_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        budgets = _budgets(payload)
        record = budgets.get(incident_id)
        if record is None:
            return _decision("owner_decision", "incident_budget_missing")
        operations = record.get("operations", {})
        if not isinstance(operations, Mapping):
            return _decision("owner_decision", "operation_accounting_corrupt")
        existing = operations.get(operation_id)
        if isinstance(existing, Mapping):
            return _decision(
                "pending", "operation_identity_replayed", receipt=existing
            )
        if policy_version != POLICY_VERSION:
            return _decision("owner_decision", "policy_version_mismatch")
        try:
            limits, _ = _trusted_policy(record.get("policy"))
            charged = _complete_usage(record.get("charged"), field="charged usage")
            reserved = _complete_usage(
                record.get("reserved", {dimension: 0 for dimension in _DIMENSIONS}),
                field="reserved usage",
            )
            origin = _time(
                record.get("original_admitted_at"), field="original admitted at"
            )
            material_bound = _current_material_is_bound(record, _actions(payload))
        except IncidentBudgetError:
            return _decision("owner_decision", "incident_accounting_corrupt")
        if record.get("status") == "awaiting_owner_decision":
            return _decision(
                "owner_decision", str(record.get("wait_reason") or "accounting_ambiguous")
            )
        if record.get("status") == "exhausted":
            return _decision("exhausted", "bounded_extension_required")
        if not material_bound:
            return _decision("owner_decision", "material_generation_unbound")
        material = None
        if kind == "review_validator":
            material = _review_validator_material(record, _actions(payload), operation_id)
            if material is None:
                return _decision("owner_decision", "review_material_unbound")
            for receipt in operations.values():
                if receipt.get("kind") != kind or receipt.get("state") != "settled":
                    continue
                observation = receipt.get("observation") or {}
                if observation.get("failure_class") != "deterministic":
                    continue
                failed_material = receipt.get("material_fingerprint")
                if failed_material is None:
                    return _decision("owner_decision", "legacy_review_material_unverified")
                if failed_material == material:
                    return _decision("pending", "deterministic_material_unchanged")
        next_eligible = record.get("next_eligible_at")
        if next_eligible is not None:
            try:
                if stamped < _time(next_eligible, field="next eligible at"):
                    return _decision("pending", "transient_backoff")
            except IncidentBudgetError:
                return _decision("owner_decision", "incident_accounting_corrupt")
        elapsed = max(0, int((stamped - origin).total_seconds()))
        if elapsed >= limits["elapsed_seconds"]:
            record_incident_budget_exhaustion(
                incident_id, "elapsed deadline consumed", root=repo, now=stamped
            )
            return _decision("exhausted", "elapsed_deadline_exhausted")
        live_claim = record.get("live_claim")
        if live_claim is not None and not isinstance(live_claim, Mapping):
            return _decision("owner_decision", "claim_accounting_corrupt")
        if isinstance(live_claim, Mapping) and live_claim.get("claim_id") != claim_id:
            reason = (
                "dead_claim_requires_reconciliation"
                if review_owner_exited(live_claim.get("owner_process"))
                else "live_incident_claim"
            )
            state: OperationDecisionState = (
                "owner_decision" if reason.startswith("dead_") else "pending"
            )
            return _decision(state, reason)
        active_receipts = [
            receipt
            for receipt in operations.values()
            if isinstance(receipt, Mapping) and receipt.get("state") == "reserved"
        ]
        # Watchdog and provider operations can be outer envelopes.  A provider
        # may synchronously invoke one explicitly linked MCP/tool operation;
        # unrelated callers and further nesting still wait.  The durable
        # parent identity prevents a shared claim string from authorizing the
        # child by itself.
        nested_active = [
            receipt
            for receipt in active_receipts
            if not str(receipt.get("kind", "")).startswith("watchdog_owner:")
        ]
        requested_parent = (
            launch_attributes.get("parent_operation_id")
            if launch_attributes is not None
            else None
        )
        provider_parent = (
            nested_active[0]
            if len(nested_active) == 1
            and str(nested_active[0].get("kind", "")).startswith("provider_turn:")
            else None
        )
        linked_provider_child = (
            provider_parent is not None
            and requested_parent == provider_parent.get("operation_id")
            and provider_parent.get("claim_id") == claim_id
            and not kind.startswith(("provider_turn:", "watchdog_owner:"))
        )
        if (
            (nested_active and not linked_provider_child)
            or len(nested_active) > 1
            or (active_receipts and kind.startswith("watchdog_owner:"))
        ):
            return _decision("pending", "serialized_operation_in_flight")
        unavailable = [
            dimension
            for dimension in _DIMENSIONS
            if dimension != "elapsed_seconds"
            and charged[dimension] + reserved[dimension] + requested[dimension]
            > limits[dimension]
        ]
        if unavailable:
            record_incident_budget_exhaustion(
                incident_id,
                f"cumulative allowance exhausted: {','.join(unavailable)}",
                root=repo,
                now=stamped,
            )
            return _decision("exhausted", "cumulative_allowance_exhausted")
        receipt_id = _operation_receipt_id(incident_id, operation_id)
        receipt = {
            "receipt_id": receipt_id,
            "operation_id": operation_id,
            "kind": kind,
            "claim_id": claim_id,
            "policy_version": POLICY_VERSION,
            "reserved": requested,
            "state": "reserved",
            "started_at": stamped.isoformat(),
            "owner_process": current_review_owner(),
        }
        if material is not None:
            receipt["material_fingerprint"] = material
        if launch_attributes is not None:
            receipt["attributes"] = launch_attributes
        operations = dict(operations)
        operations[operation_id] = receipt
        record["operations"] = operations
        record["reserved"] = {
            dimension: reserved[dimension] + requested[dimension]
            for dimension in _DIMENSIONS
        }
        record["charged"] = {**charged, "elapsed_seconds": elapsed}
        if live_claim is None:
            record["live_claim"] = {
                "claim_id": claim_id,
                "owner_process": receipt["owner_process"],
                "started_at": stamped.isoformat(),
            }
        budgets[incident_id] = record
        payload["incident_budgets"] = budgets
        _write_payload(repo, payload)
        permit = IncidentOperationPermit(
            incident_id,
            operation_id,
            claim_id,
            POLICY_VERSION,
            _copy(requested),
            receipt_id,
        )
        return _decision("admitted", "bounded_permit_reserved", receipt=receipt, permit=permit)


def settle_incident_operation(
    incident_id: str,
    operation_id: str,
    observation: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> IncidentOperationDecision:
    """Settle one receipt exactly once, conservatively retaining uncertainty."""

    incident_id = _identity(incident_id, field="incident identity")
    operation_id = _identity(operation_id, field="operation identity")
    facts = _json_mapping(observation, field="operation observation")
    usage_value = facts.get("usage", {})
    if not isinstance(usage_value, Mapping):
        raise IncidentBudgetError("operation observation usage must be a mapping")
    actual = _usage(usage_value, allow_zero=True, field="observed usage")
    quality = facts.get("quality", "known")
    if quality not in {"known", "estimated", "unavailable"}:
        raise IncidentBudgetError("observation quality is unsupported")
    outcome = facts.get("outcome", "success")
    if outcome not in {"success", "error", "timeout", "interrupted", "unknown"}:
        raise IncidentBudgetError("operation outcome is unsupported")
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    repo = resolve_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        budgets = _budgets(payload)
        record = budgets.get(incident_id)
        if record is None:
            return _decision("owner_decision", "incident_budget_missing")
        operations = record.get("operations")
        if not isinstance(operations, Mapping):
            return _decision("owner_decision", "operation_accounting_corrupt")
        receipt_value = operations.get(operation_id)
        if not isinstance(receipt_value, Mapping):
            return _decision("owner_decision", "operation_receipt_missing")
        receipt = dict(receipt_value)
        if receipt.get("state") == "settled":
            return _decision("admitted", "operation_already_settled", receipt=receipt)
        if receipt.get("state") != "reserved":
            return _decision("owner_decision", "operation_receipt_corrupt", receipt=receipt)
        try:
            reserved_for_operation = _complete_usage(
                receipt.get("reserved"), field="operation reservation"
            )
            reserved = _complete_usage(record.get("reserved"), field="reserved usage")
            charged = _complete_usage(record.get("charged"), field="charged usage")
            origin = _time(
                record.get("original_admitted_at"), field="original admitted at"
            )
            limits, _ = _trusted_policy(record.get("policy"))
        except IncidentBudgetError:
            return _decision("owner_decision", "incident_accounting_corrupt")
        # Unavailable observations cannot release a worst-case reservation as
        # though zero use had been measured.  This is especially important for
        # providers whose transports expose no token or remote-runtime usage.
        conservative = outcome in {"interrupted", "unknown"} or (
            quality == "unavailable" and facts.get("provider_started") is not False
        )
        applied = (
            dict(reserved_for_operation)
            if conservative
            else {
                dimension: max(actual[dimension], 0)
                for dimension in _DIMENSIONS
            }
        )
        elapsed = max(0, int((stamped - origin).total_seconds()))
        applied["elapsed_seconds"] = elapsed
        record["reserved"] = {
            dimension: max(0, reserved[dimension] - reserved_for_operation[dimension])
            for dimension in _DIMENSIONS
        }
        record["charged"] = {
            dimension: (
                max(charged[dimension], elapsed)
                if dimension == "elapsed_seconds"
                else charged[dimension] + applied[dimension]
            )
            for dimension in _DIMENSIONS
        }
        receipt.update(
            state="settled",
            settled_at=stamped.isoformat(),
            observation=facts,
            charged=applied,
            consumption_quality="unavailable" if conservative else quality,
        )
        operations = dict(operations)
        operations[operation_id] = receipt
        record["operations"] = operations
        if quality != "known" or conservative:
            record["consumption_quality"] = (
                "unavailable" if conservative or quality == "unavailable" else "estimated"
            )
        failure_class = facts.get("failure_class")
        if outcome != "success":
            if outcome in {"interrupted", "unknown"}:
                record["status"] = "awaiting_owner_decision"
                record["wait_reason"] = "in_flight_usage_reconciliation_required"
            elif failure_class == "transient":
                failures = int(record.get("transient_failures") or 0) + 1
                record["transient_failures"] = failures
                if failures < RETRY_POLICY["transient_attempts"]:
                    delay = _backoff_seconds(operation_id, failures)
                    record["next_eligible_at"] = (
                        stamped + timedelta(seconds=delay)
                    ).isoformat()
                else:
                    _exhaust(record, "transient attempts exhausted", stamped)
            elif failure_class == "deterministic":
                # A review validator receipt fences these exact inputs. A new
                # material generation may use only the remaining original budget.
                if receipt.get("kind") != "review_validator" or not receipt.get("material_fingerprint"):
                    _exhaust(record, "deterministic failure exhausted", stamped)
            else:
                record["status"] = "awaiting_owner_decision"
                record["wait_reason"] = "failure_classification_unknown"
        else:
            record.pop("next_eligible_at", None)
        if facts.get("claim_complete") is True:
            record["live_claim"] = None
        if any(
            record["charged"][dimension] >= limits[dimension]
            for dimension in _DIMENSIONS
        ):
            _exhaust(record, "settled allowance exhausted", stamped)
        budgets[incident_id] = record
        payload["incident_budgets"] = budgets
        _write_payload(repo, payload)
        state: OperationDecisionState = (
            "exhausted"
            if record.get("status") == "exhausted"
            else "owner_decision"
            if record.get("status") == "awaiting_owner_decision"
            else "admitted"
        )
        return _decision(state, "operation_settled", receipt=receipt)


def read_incident_budget(incident_id: str, *, root: Path) -> dict[str, Any] | None:
    """Read one budget without creating lifecycle state or spending allowance."""

    incident_id = _identity(incident_id, field="incident identity")
    repo = resolve_root(root)
    with task_lifecycle_read_lock(root=repo):
        record = _budgets(_read_payload(repo)).get(incident_id)
    return _project(record) if record is not None else None


def extend_incident_budget(
    incident_id: str,
    authenticated_authority: AuthenticatedHuman,
    reason: str,
    evidence: Mapping[str, Any],
    finite_additions: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append one independently authenticated, finite, bounded extension."""

    incident_id = _identity(incident_id, field="incident identity")
    reason = _identity(reason, field="extension reason")
    if not isinstance(authenticated_authority, AuthenticatedHuman):
        raise IncidentBudgetAuthorityError(
            "an authenticated human authority must grant an extension"
        )
    facts = _json_mapping(evidence, field="extension evidence")
    additions = _usage(finite_additions, allow_zero=False, field="finite additions")
    if not any(additions.values()):
        raise IncidentBudgetError("an extension must add finite allowance")
    repo = resolve_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        budgets = _budgets(payload)
        record = budgets.get(incident_id)
        if record is None:
            raise IncidentBudgetError("incident budget does not exist")
        owner = record.get("accountable_owner")
        owner_work_id = owner.get("work_id") if isinstance(owner, Mapping) else None
        if authenticated_authority.subject in {owner_work_id, f"team:{owner_work_id}"}:
            raise IncidentBudgetAuthorityError(
                "the recovering team cannot extend its own incident"
            )
        policy = record.get("policy")
        limits, maxima = _trusted_policy(policy)
        receipt_material = json.dumps(
            {
                "incident_id": incident_id,
                "authority": authenticated_authority.subject,
                "reason": reason,
                "evidence": facts,
                "additions": additions,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        receipt_id = "sha256:" + hashlib.sha256(receipt_material.encode()).hexdigest()
        extensions = list(record.get("extensions") or [])
        if any(
            isinstance(item, Mapping) and item.get("receipt_id") == receipt_id
            for item in extensions
        ):
            return _project(record)
        for dimension, amount in additions.items():
            if limits[dimension] + amount > maxima[dimension]:
                raise IncidentBudgetError(
                    f"extension exceeds trusted maximum for {dimension}"
                )
        if additions:
            extensions.append(
                {
                    "receipt_id": receipt_id,
                    "authority": authenticated_authority.subject,
                    "reason": reason,
                    "evidence": facts,
                    "additions": additions,
                    "recorded_at": _iso(now),
                }
            )
            policy = dict(policy)
            policy["limits"] = {
                dimension: limits[dimension] + additions[dimension]
                for dimension in _DIMENSIONS
            }
            record["policy"] = policy
            record["extensions"] = extensions
            if record.get("status") == "exhausted":
                charged = _usage(
                    record.get("charged", {}),
                    allow_zero=True,
                    field="charged usage",
                )
                if all(
                    charged[dimension] < policy["limits"][dimension]
                    for dimension in _DIMENSIONS
                ):
                    record["status"] = "active"
                    record["wait_reason"] = None
            budgets[incident_id] = record
            payload["incident_budgets"] = budgets
            _write_payload(repo, payload)
        return _project(record)


def record_incident_budget_exhaustion(
    incident_id: str,
    reason: str,
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist exactly one escalation identity for exhausted allowance."""

    incident_id = _identity(incident_id, field="incident identity")
    reason = _identity(reason, field="exhaustion reason")
    repo = resolve_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        budgets = _budgets(payload)
        record = budgets.get(incident_id)
        if record is None:
            raise IncidentBudgetError("incident budget does not exist")
        if record.get("escalation_id") is None:
            record["escalation_id"] = _escalation_id(incident_id)
            record["exhausted_at"] = _iso(now)
            record["exhaustion_reason"] = reason
        record["status"] = "exhausted"
        record["wait_reason"] = "bounded_extension_required"
        budgets[incident_id] = record
        payload["incident_budgets"] = budgets
        _write_payload(repo, payload)
        return _project(record)


def _project(record: Mapping[str, Any]) -> dict[str, Any]:
    result = _copy(dict(record))
    policy = result.get("policy")
    limits, _ = _trusted_policy(policy)
    charged = _complete_usage(result.get("charged"), field="charged usage")
    reserved = _complete_usage(
        result.get("reserved", {dimension: 0 for dimension in _DIMENSIONS}),
        field="reserved usage",
    )
    result["reserved"] = reserved
    result.setdefault("operations", {})
    result.setdefault("live_claim", None)
    result["remaining"] = {
        dimension: max(0, limits[dimension] - charged[dimension] - reserved[dimension])
        for dimension in _DIMENSIONS
    }
    return result


__all__ = [
    "DEFAULT_LIMITS",
    "MAXIMUM_LIMITS",
    "POLICY_ID",
    "POLICY_VERSION",
    "RETRY_POLICY",
    "IncidentBudgetAuthorityError",
    "IncidentBudgetError",
    "IncidentOperationDecision",
    "IncidentOperationPermit",
    "bind_incident_budget",
    "extend_incident_budget",
    "read_incident_budget",
    "record_incident_budget_exhaustion",
    "reserve_incident_operation",
    "settle_incident_operation",
]
