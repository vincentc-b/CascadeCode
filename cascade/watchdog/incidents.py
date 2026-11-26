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
RecoveryStage = Literal[
    "detected",
    "admitted",
    "assigned",
    "executing",
    "validating",
    "publishing",
    "verifying",
    "resolved",
    "waiting",
]

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
    original_incident_id: str | None = None,
    stage_receipts: Sequence[Mapping[str, Any]] = (),
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
    if original_incident_id is not None and (
        not isinstance(original_incident_id, str)
        or not original_incident_id
        or original_incident_id.strip() != original_incident_id
    ):
        raise ValueError("original incident identity must be a nonempty stable string")
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    retry_at = None
    claim_expires_at = None
    if outcome == "claimed":
        claim_expires_at = (stamped + timedelta(seconds=claim_seconds)).isoformat()
    elif outcome != "success":
        retry_at = (stamped + timedelta(seconds=reassessment_seconds)).isoformat()
    normalized_stages = _transition_stage_receipts(
        stage_receipts,
        work_id=work_id,
        failure_class=failure_class,
        generation=generation,
        original_incident_id=original_incident_id,
        attempts=attempts,
    )
    return {
        "schema_version": 1,
        "work_id": work_id,
        "tier": tier,
        "work": {"work_id": work_id, "tier": tier},
        "accountable_owner": accountable_owner,
        "failure_class": failure_class,
        "authoritative_generation": generation,
        "original_incident_id": original_incident_id,
        "evidence": _json_copy(evidence),
        "selected_capability": selected_capability,
        "request": _json_copy(request or {}),
        "acknowledgement": _json_copy(acknowledgement or {}),
        "result": _json_copy(result or {}),
        "attempts": [_json_copy(item) for item in attempts],
        "stage_receipts": normalized_stages,
        # Stage receipts are already immutable and safe, so they are the
        # Watchdog's canonical transition receipts rather than a duplicate log.
        "transition_receipts": normalized_stages,
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


def recovery_stage_receipt(
    stage: RecoveryStage,
    *,
    actor: str,
    capability: str,
    permitted_inputs: Sequence[str],
    authority_revision: str,
    obligation: str,
    result: str,
    now: datetime | None = None,
    verification_reference: str | None = None,
) -> dict[str, Any]:
    """Build one attributable, immutable cross-stage recovery receipt."""

    if stage not in RecoveryStage.__args__:
        raise ValueError("unknown recovery stage")
    values = (actor, capability, authority_revision, obligation, result)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("stage actor, capability, authority and result are required")
    inputs = tuple(dict.fromkeys(permitted_inputs))
    if not inputs or not all(
        isinstance(value, str) and value.strip() for value in inputs
    ):
        raise ValueError("stage permitted inputs must be explicit")
    identity = {
        "stage": stage,
        "actor": actor,
        "capability": capability,
        "permitted_inputs": list(inputs),
        "authority_revision": authority_revision,
        "obligation": obligation,
        "result": result,
        "verification_reference": verification_reference,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "receipt_id": "sha256:" + hashlib.sha256(encoded.encode()).hexdigest(),
        **identity,
        "recorded_at": stamped.isoformat(),
    }


def append_stage_receipts(
    existing: Sequence[Mapping[str, Any]],
    *receipts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Append stage evidence without rewriting earlier receipts.

    A call represents a material persisted transition.  Equal text and equal
    timestamps therefore remain distinct; incident_record assigns their stable
    per-source sequence and final v1 identity.
    """

    result = [_json_copy(item) for item in existing]
    for receipt in receipts:
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            raise ValueError("stage receipt identity is required")
        result.append(_json_copy(receipt))
    return result


def transition_receipt_v1(
    *,
    source_kind: str,
    source_key: str,
    action: str,
    action_id: str,
    generation: str,
    sequence: int,
    transition_kind: str,
    occurred_at: str | None,
    source_reference: str,
    original_incident_id: str | None = None,
    graph_id: str | None = None,
    affected_work_ids: Sequence[str] = (),
    attempt_number: int | None = None,
    claim_id: str | None = None,
    safe_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared immutable source-transition contract."""

    required = (source_kind, source_key, action, action_id, generation,
                transition_kind, source_reference)
    if not all(isinstance(value, str) and value.strip() for value in required):
        raise ValueError("transition receipt identity fields are required")
    if sequence < 1:
        raise ValueError("transition receipt sequence must be positive")
    work_ids = tuple(dict.fromkeys(str(item) for item in affected_work_ids if item))
    identity = {
        "source_kind": source_kind,
        "source_key": source_key,
        "action": action,
        "action_id": action_id,
        "original_incident_id": original_incident_id,
        "generation": generation,
        "graph_id": graph_id,
        "affected_work_ids": list(work_ids),
        "attempt_number": attempt_number,
        "claim_id": claim_id,
        "transition_sequence": sequence,
        "transition_kind": transition_kind,
        "source_reference": source_reference,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": 1,
        "receipt_id": "sha256:" + hashlib.sha256(encoded.encode()).hexdigest(),
        **identity,
        "occurred_at": occurred_at,
        "safe_payload": _json_copy(safe_payload or {}),
    }


def _transition_stage_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    work_id: str,
    failure_class: str,
    generation: str,
    original_incident_id: str | None,
    attempts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich retained stage evidence with the shared v1 source identity."""

    source_key = f"{work_id}:{failure_class}:{generation}"
    latest = dict(attempts[-1]) if attempts else {}
    claim_id = latest.get("claim_token")
    attempt_number = latest.get("attempt")
    result: list[dict[str, Any]] = []
    for sequence, raw in enumerate(receipts, start=1):
        receipt = _json_copy(raw)
        if receipt.get("schema_version") == 1 and receipt.get("transition_sequence") == sequence:
            result.append(receipt)
            continue
        stage = str(receipt.get("stage") or "waiting")
        result.append(
            {
                **receipt,
                **transition_receipt_v1(
                    source_kind="watchdog_incident",
                    source_key=source_key,
                    action=str(receipt.get("capability") or "watchdog_recovery"),
                    action_id=source_key,
                    original_incident_id=original_incident_id,
                    generation=generation,
                    graph_id=work_id,
                    affected_work_ids=(work_id,),
                    attempt_number=(int(attempt_number) if attempt_number is not None else None),
                    claim_id=(str(claim_id) if claim_id is not None else None),
                    sequence=sequence,
                    transition_kind=stage,
                    occurred_at=(str(receipt["recorded_at"]) if receipt.get("recorded_at") else None),
                    source_reference=f"incident:{source_key}:stage:{sequence}",
                    safe_payload={
                        key: receipt.get(key)
                        for key in ("stage", "actor", "capability", "result", "verification_reference")
                        if receipt.get(key) is not None
                    },
                ),
            }
        )
    return result


def incident_budget_identity(incident: Mapping[str, Any]) -> str | None:
    """Return the separately bound original identity without inventing one."""

    value = incident.get("original_incident_id")
    if value is None:
        return None
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError("original incident identity is malformed")
    if value == incident.get("authoritative_generation"):
        raise ValueError("incident identity cannot be its material generation")
    return value


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
        prior_success = max(
            successes, key=lambda item: str(item.get("recorded_at") or "")
        )
        return IncidentEligibility(
            "suppressed", "terminal_success", generation, prior_success
        )
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
    "append_stage_receipts",
    "authoritative_generation",
    "capability_authority_fingerprint",
    "incident_record",
    "incident_budget_identity",
    "project_incident",
    "recovery_stage_receipt",
    "transition_receipt_v1",
]
