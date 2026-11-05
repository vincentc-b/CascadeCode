"""Provider-independent recovery hand-off for Feature and Epic team turns.

Providers are only allowed to receive a previously reconciled action.  This
keeps a retry tied to the same durable identity and gives callers one result
shape regardless of whether the turn was launched through Cursor, Claude, or
Codex.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping

if TYPE_CHECKING:
    from cascade.task.action_recovery import ActionReconciliation

RecoveryOutcome = Literal["resume", "safe_retry", "completed", "blocked"]


def _json_object(value: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    try:
        copied = json.loads(json.dumps(dict(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be JSON serializable") from exc
    if not isinstance(copied, dict):  # defensive: json decoders are extensible
        raise ValueError(f"{name} must be an object")
    return copied


@dataclass(frozen=True)
class ProviderRecoveryLaunch:
    """The exact durable action/checkpoint supplied to every provider.

    ``evidence`` is intentionally provider-neutral.  A caller obtains it from
    the action recovery record before starting a provider process; providers
    must not replace it with an unverified local interpretation.
    """

    action_id: str
    checkpoint_id: str
    outcome: RecoveryOutcome
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.action_id or self.action_id.strip() != self.action_id:
            raise ValueError("recovery action_id must be a nonempty stable string")
        if not self.checkpoint_id or self.checkpoint_id.strip() != self.checkpoint_id:
            raise ValueError("recovery checkpoint_id must be a nonempty stable string")
        if self.outcome not in {"resume", "safe_retry", "completed", "blocked"}:
            raise ValueError(f"unknown recovery outcome: {self.outcome}")
        object.__setattr__(self, "evidence", _json_object(self.evidence, name="recovery evidence"))

    def prompt_block(self) -> str:
        """Stable, provider-agnostic launch input included in the turn prompt."""

        return "Provider recovery contract:\n" + json.dumps(
            {
                "action_id": self.action_id,
                "checkpoint_id": self.checkpoint_id,
                "outcome": self.outcome,
                "evidence": self.evidence,
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class ProviderRecoveryReport:
    """Normalized result reported by every Feature/Epic provider adapter."""

    action_id: str
    checkpoint_id: str
    outcome: RecoveryOutcome
    provider: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.action_id or not self.checkpoint_id:
            raise ValueError("recovery reports require action and checkpoint identities")
        if self.outcome not in {"resume", "safe_retry", "completed", "blocked"}:
            raise ValueError(f"unknown recovery outcome: {self.outcome}")
        object.__setattr__(self, "evidence", _json_object(self.evidence, name="recovery report evidence"))


def launch_from_reconciliation(
    reconciliation: ActionReconciliation,
    *,
    evidence: Mapping[str, Any],
) -> ProviderRecoveryLaunch:
    """Convert the durable reconciliation vocabulary into the provider vocabulary."""

    checkpoint_id = reconciliation.checkpoint_id
    if not checkpoint_id:
        raise ValueError("provider recovery launch requires a durable checkpoint")
    outcome: RecoveryOutcome
    if reconciliation.outcome == "already_completed":
        outcome = "completed"
    elif reconciliation.outcome in {"resume", "safe_retry", "blocker"}:
        outcome = reconciliation.outcome
    else:  # protects this boundary if the durable vocabulary is extended
        raise ValueError(f"unsupported reconciliation outcome: {reconciliation.outcome}")
    merged = dict(evidence)
    merged.setdefault("reason", reconciliation.reason)
    merged.setdefault("affected_paths", list(reconciliation.affected_paths))
    merged.setdefault("resume_instructions", reconciliation.resume_instructions or "")
    return ProviderRecoveryLaunch(reconciliation.action_id, checkpoint_id, outcome, merged)


def report_provider_recovery(
    launch: ProviderRecoveryLaunch,
    *,
    provider: str,
    status: str,
) -> ProviderRecoveryReport:
    """Return one result contract without trusting provider-specific labels.

    A finished resume/retry has completed the provider turn.  Errors are an
    evidenced blocker and retain the original checkpoint rather than allowing a
    provider to invent a new action identity.  Terminal decisions never launch
    a provider and retain their already-reconciled outcome.
    """

    evidence = dict(launch.evidence)
    evidence.update({"provider": provider, "provider_status": status})
    if launch.outcome in {"completed", "blocked"}:
        outcome = launch.outcome
    elif status == "finished":
        outcome = "completed"
    else:
        outcome = "blocked"
        evidence.setdefault("reason", "provider_turn_failed")
    return ProviderRecoveryReport(
        launch.action_id, launch.checkpoint_id, outcome, provider, evidence
    )

