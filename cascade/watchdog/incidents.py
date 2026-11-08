"""Shared generation-aware incident records for existing recovery ledgers.

The record in this module is an additive envelope.  It does not replace the
authoritative board, execution, action, or review state kept by their owning
subsystems.  Recovery stores may embed the envelope while retaining every
legacy field their existing readers require.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, Sequence

from cascade.board.types import WorkTier
from cascade.board.work_ids import parse_work_id_parts

IncidentOutcome = Literal[
    "claimed", "success", "error", "refused", "deferred", "unsafe", "no_op"
]
EligibilityState = Literal["eligible", "cooldown", "suppressed"]

_OUTCOMES = frozenset(IncidentOutcome.__args__)
DEFAULT_REASSESSMENT_SECONDS = 60
DEFAULT_CLAIM_SECONDS = 300


@dataclass(frozen=True, slots=True)
class IncidentEligibility:
    state: EligibilityState
    reason: str
    generation: str
    prior: Mapping[str, Any] | None = None

    @property
    def eligible(self) -> bool:
        return self.state == "eligible"


def authoritative_generation(
    *,
    work_id: str,
    tier: WorkTier,
    evidence: Mapping[str, Any],
    capability: str,
    capability_fingerprint: str | None = None,
) -> str:
    """Fingerprint every authoritative input supplied by the owning adapter."""

    _validate_work(work_id, tier)
    if not capability:
        raise ValueError("incident capability is required")
    payload = {
        "work": {"work_id": work_id, "tier": tier},
        "evidence": _json_copy(evidence),
        "capability": capability,
        "capability_fingerprint": capability_fingerprint,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def capability_authority_fingerprint() -> str:
    """Fingerprint the currently registered recovery authority contract.

    The import is intentionally deferred: capability descriptors bind existing
    action-recovery callables, while action recovery also embeds this value in
    its incident generation.  Deferring avoids a module import cycle and keeps
    the helper read-only.
    """

    from cascade.watchdog.capabilities import default_capability_registry

    return default_capability_registry().fingerprint()


def incident_record(
    *,
    work_id: str,
    tier: WorkTier,
    accountable_owner: str,
    failure_class: str,
    generation: str,
    evidence: Mapping[str, Any],
    selected_capability: str,
    request: Mapping[str, Any] | None = None,
    acknowledgement: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    attempts: Sequence[Mapping[str, Any]] = (),
    outcome: IncidentOutcome,
    now: datetime | None = None,
    reassessment_seconds: int = DEFAULT_REASSESSMENT_SECONDS,
    claim_seconds: int = DEFAULT_CLAIM_SECONDS,
    attempt_bound: int = 3,
) -> dict[str, Any]:
    """Build the common JSON record embedded by each existing ledger."""

    _validate_work(work_id, tier)
    if not accountable_owner:
        raise ValueError("incident accountable_owner is required")
    if not failure_class:
        raise ValueError("incident failure_class is required")
    if not selected_capability:
        raise ValueError("incident selected_capability is required")
    if outcome not in _OUTCOMES:
        raise ValueError(f"unknown incident outcome: {outcome}")
    if not _valid_generation(generation):
        raise ValueError("incident generation must be a full sha256 identity")
    if reassessment_seconds < 1 or claim_seconds < 1 or attempt_bound < 1:
        raise ValueError("incident retry policy values must be positive")
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    retry_at = None
    claim_expires_at = None
    if outcome == "claimed":
        claim_expires_at = (stamped + timedelta(seconds=claim_seconds)).isoformat()
    elif outcome != "success":
        retry_at = (stamped + timedelta(seconds=reassessment_seconds)).isoformat()
    return {
        "schema_version": 1,
        "work_id": work_id,
        "tier": tier,
        "work": {"work_id": work_id, "tier": tier},
        "accountable_owner": accountable_owner,
        "failure_class": failure_class,
        "authoritative_generation": generation,
        "evidence": _json_copy(evidence),
        "selected_capability": selected_capability,
        "request": _json_copy(request or {}),
        "acknowledgement": _json_copy(acknowledgement or {}),
        "result": _json_copy(result or {}),
        "attempts": [_json_copy(item) for item in attempts],
        "retry_policy": {
            "reassessment_seconds": reassessment_seconds,
            "claim_seconds": claim_seconds,
            "attempt_bound": attempt_bound,
        },
        "claim_expires_at": claim_expires_at,
        "next_reassessment_at": retry_at,
        "outcome": outcome,
        "recorded_at": stamped.isoformat(),
    }


def project_incident(
    observation: object,
    ledger: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    failure_class: str | None = None,
    now: datetime | None = None,
) -> IncidentEligibility:
    """Project retry eligibility for an audit observation without writing.

    Legacy rows and records from another generation are deliberately eligible.
    Only success for the exact authoritative generation is permanent.
    """

    generation = _observation_generation(observation)
    if failure_class is None:
        incident = getattr(observation, "incident", observation)
        failure_class = getattr(incident, "failure_class", None)
    rows = ledger.values() if isinstance(ledger, Mapping) else ledger
    matching: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if isinstance(row.get("incident_contract"), Mapping):
            candidate = row["incident_contract"]
        else:
            candidate = (
                row.get("incident") if isinstance(row.get("incident"), Mapping) else row
            )
        if candidate.get("authoritative_generation") == generation and (
            failure_class is None or candidate.get("failure_class") == failure_class
        ):
            matching.append(candidate)
    if not matching:
        return IncidentEligibility("eligible", "new_or_changed_generation", generation)
    successes = [row for row in matching if row.get("outcome") == "success"]
    if successes:
        prior_success = max(successes, key=lambda item: str(item.get("recorded_at") or ""))
        return IncidentEligibility("suppressed", "terminal_success", generation, prior_success)
    prior = max(matching, key=lambda item: str(item.get("recorded_at") or ""))
    outcome = prior.get("outcome")
    deadline_name = (
        "claim_expires_at" if outcome == "claimed" else "next_reassessment_at"
    )
    deadline = _parse_time(prior.get(deadline_name))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if deadline is not None and current < deadline:
        return IncidentEligibility("cooldown", f"{outcome}_cooldown", generation, prior)
    return IncidentEligibility(
        "eligible", f"{outcome or 'legacy'}_expired", generation, prior
    )


def append_generation_history(row: dict[str, Any], contract: Mapping[str, Any]) -> None:
    """Install a contract while retaining the prior generation in the same row."""

    previous = row.get("incident")
    if isinstance(previous, Mapping) and (
        previous.get("authoritative_generation")
        != contract.get("authoritative_generation")
    ):
        history = list(row.get("incident_history") or [])
        history.append(_json_copy(previous))
        row["incident_history"] = history
    row["incident"] = _json_copy(contract)


def _observation_generation(observation: object) -> str:
    generation = (
        observation
        if isinstance(observation, str)
        else getattr(observation, "generation", None)
    )
    value = getattr(generation, "value", generation)
    if not _valid_generation(value):
        raise ValueError("observation has no valid authoritative generation")
    return value


def _valid_generation(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _validate_work(work_id: str, tier: WorkTier) -> None:
    if tier not in {"task", "feature", "epic"}:
        raise ValueError(f"unknown work tier: {tier}")
    try:
        actual = parse_work_id_parts(work_id).tier
    except Exception as exc:
        raise ValueError(f"invalid work ID: {work_id!r}") from exc
    if actual != tier:
        raise ValueError(f"{work_id!r} is a {actual} ID, not a {tier} ID")


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), sort_keys=True, default=str))


__all__ = [
    "IncidentEligibility",
    "IncidentOutcome",
    "append_generation_history",
    "authoritative_generation",
    "capability_authority_fingerprint",
    "incident_record",
    "project_incident",
]
