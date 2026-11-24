"""Durable cumulative policy for one original recovery incident.

The budget is an additive collection in the existing action ledger.  This
module deliberately owns lineage and policy only; operation reservation and
settlement are separate admission concerns.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cascade.board.context import resolve_root
from cascade.epic.dependency_approvals import AuthenticatedHuman
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


def _iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


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
    supplied = evidence.get("legacy_usage")
    if supplied is not None:
        if not isinstance(supplied, Mapping):
            raise IncidentBudgetError("legacy_usage must be a mapping")
        usage = _usage(supplied, allow_zero=True, field="legacy usage")
        if usage["tool_attempts"] < len(attempts):
            raise IncidentBudgetError("legacy usage cannot omit recorded attempts")
        return usage, "known", None
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
            if legacy_lineage_wait is not None:
                quality = "unavailable"
                wait_reason = legacy_lineage_wait
            admitted_at = _iso(now)
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
    result["remaining"] = {
        dimension: max(0, limits[dimension] - charged[dimension])
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
    "bind_incident_budget",
    "extend_incident_budget",
    "read_incident_budget",
    "record_incident_budget_exhaustion",
]
