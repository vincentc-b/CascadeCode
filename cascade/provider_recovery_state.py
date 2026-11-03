"""Shared, safe provider-recovery state for board and War Room consumers.

The execution boundary stores only a compact provider blocker.  This module is
the presentation contract layered over that durable record: it never exposes a
provider exception or credential detail, and it keeps recovery controls
separate from the Epic return-to-backlog lifecycle transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


RecoveryActionName = Literal[
    "change_provider", "retry", "provider_setup", "return_to_backlog"
]

_SAFE_REASONS = {
    "provider_unavailable": "The selected provider is unavailable. Check provider setup or credentials, then retry.",
    "model_not_offered": "The selected model is not offered by the provider. Choose a supported provider or model.",
    "reasoning_not_supported": "The selected reasoning level is not supported by this provider and model.",
    "flex_mode_not_supported": "The selected provider does not support flex mode.",
    "invalid_model": "The selected model is invalid.",
    "invalid_tier": "The work item has an unsupported provider configuration.",
}
_UNKNOWN_REASON = "The provider could not start this work item. Review the provider selection and try again."


def safe_provider_reason(reason_code: object) -> str:
    """Return an operator-readable reason without provider-supplied detail."""

    return _SAFE_REASONS.get(reason_code, _UNKNOWN_REASON)


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    """One explicit control contract, including a fail-closed refusal."""

    eligible: bool
    reason_code: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"eligible": self.eligible}
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def recovery_actions(
    *,
    tier: str,
    status: str,
    blocker: Mapping[str, object] | None,
    turn_stoppable: bool | None,
    return_to_backlog: Mapping[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    """Evaluate control eligibility from an authoritative read-only snapshot.

    A Task's Git cleanliness is deliberately absent here: changing a provider
    and retrying only update selection/turn state and must preserve either a
    clean or dirty worktree.  Return-to-backlog remains the separately supplied
    Epic graph eligibility contract, which is where dirty descendants matter.
    """

    active = status == "active"
    blocked = bool(blocker and blocker.get("active"))
    retryable = blocked and blocker.get("classification") == "transient"
    can_stop = turn_stoppable is True

    def turn_action(base: bool) -> RecoveryAction:
        if not active:
            return RecoveryAction(False, "not_active", "Provider recovery is only available for active work.")
        if not blocked:
            return RecoveryAction(False, "no_provider_blocker", "No active provider recovery is required.")
        if not can_stop:
            return RecoveryAction(False, "turn_not_stoppable", "The active turn cannot be stopped safely yet.")
        return RecoveryAction(base)

    retry = turn_action(retryable)
    if retry.eligible is False and active and blocked and can_stop and not retryable:
        retry = RecoveryAction(False, "selection_change_required", "Choose a supported provider or model before retrying.")

    setup = (
        RecoveryAction(True)
        if active and blocked and retryable
        else RecoveryAction(
            False,
            "provider_setup_not_required",
            "Provider setup guidance is only needed for a transient provider failure.",
        )
    )
    if tier != "epic":
        returned = RecoveryAction(False, "not_epic", "Return to backlog is an Epic lifecycle action.")
    elif return_to_backlog is None:
        returned = RecoveryAction(False, "return_eligibility_unknown", "Return-to-backlog eligibility could not be determined safely.")
    elif return_to_backlog.get("eligible") is True:
        returned = RecoveryAction(True)
    else:
        returned = RecoveryAction(False, "return_not_eligible", "The Epic is not eligible to return to backlog.")

    return {
        "change_provider": turn_action(True).to_dict(),
        "retry": retry.to_dict(),
        "provider_setup": setup.to_dict(),
        "return_to_backlog": returned.to_dict(),
    }


def provider_recovery_state(
    blocker: Mapping[str, object] | None,
    *,
    tier: str,
    status: str,
    turn_stoppable: bool | None,
    return_to_backlog: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    """Serialize one durable blocker and its action contract for an API row."""

    if not blocker or not blocker.get("active"):
        return None
    reason_code = blocker.get("reason_code")
    code = reason_code if isinstance(reason_code, str) else "provider_unavailable"
    return {
        "work_id": blocker.get("work_id"),
        "tier": tier,
        "active": True,
        "classification": blocker.get("classification"),
        "reason_code": code,
        "reason": safe_provider_reason(code),
        "recommended_remedy": blocker.get("recommended_remedy"),
        "affected_roles": list(blocker.get("affected_roles") or ()),
        "first_attempt": blocker.get("first_attempt"),
        "last_attempt": blocker.get("last_attempt"),
        "actions": recovery_actions(
            tier=tier,
            status=status,
            blocker=blocker,
            turn_stoppable=turn_stoppable,
            return_to_backlog=return_to_backlog,
        ),
    }


__all__ = ["RecoveryAction", "RecoveryActionName", "provider_recovery_state", "recovery_actions", "safe_provider_reason"]
