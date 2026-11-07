"""Read-only eligibility for continuing one failed action without Flex.

Eligibility is deliberately separate from authorization.  This module never
persists a waiver or replays an action; it only binds a fresh, full-scope
capability result to the concrete failed action that produced the blocker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Mapping

from cascade.agent.flex_continuation_contract import OriginalActionIdentity
from cascade.agent.preflight import ProviderCapabilityBatchPreflight

EligibilityReason = Literal[
    "eligible",
    "unauthorized",
    "missing_failed_action",
    "invalid_failed_action",
    "action_mismatch",
    "selection_changed",
    "no_flex_rejection",
    "mixed_deterministic_failures",
    "inventory_not_fresh",
    "transient_blocker",
    "configuration_blocker",
    "provenance_blocker",
    "capability_blocker",
    "lifecycle_blocker",
    "approval_blocker",
]

_MESSAGES: Mapping[EligibilityReason, str] = {
    "eligible": "This failed action can be continued once with Flex disabled.",
    "unauthorized": "An explicit human authorization is required.",
    "missing_failed_action": "No concrete failed action is available for continuation.",
    "invalid_failed_action": "The failed action identity is invalid.",
    "action_mismatch": "The provider failure does not belong to this failed action.",
    "selection_changed": "The reviewed selection changed after the failed action.",
    "no_flex_rejection": "The failed action has no Flex rejection.",
    "mixed_deterministic_failures": "Another configuration failure must be resolved before continuation.",
    "inventory_not_fresh": "Fresh provider capability evidence is required.",
    "transient_blocker": "A transient provider blocker still prevents continuation.",
    "configuration_blocker": "The current agent configuration still prevents continuation.",
    "provenance_blocker": "The reviewed selection provenance no longer matches.",
    "capability_blocker": "A provider capability blocker still prevents continuation.",
    "lifecycle_blocker": "The original lifecycle action is no longer eligible.",
    "approval_blocker": "The approval required by the original action is no longer valid.",
}

_CONFIGURATION_REASONS = {
    "missing_configuration",
    "malformed_configuration",
    "invalid_model",
    "invalid_tier",
}
_PROVENANCE_REASONS = {"stale_selection"}


@dataclass(frozen=True, slots=True)
class FlexContinuationEligibility:
    """Safe command/API projection; no provider payload is retained."""

    eligible: bool
    reason_code: EligibilityReason
    reason: str
    action_id: str | None = None
    receipt_id: str | None = None
    work_id: str | None = None
    document_revision: str | None = None
    selection_fingerprint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def evaluate_flex_continuation_eligibility(
    *,
    failed_action: Mapping[str, object] | None,
    failed_preflight: Mapping[str, object] | None,
    disabled_preflight: ProviderCapabilityBatchPreflight | None,
    lifecycle_eligible: bool = True,
    approval_eligible: bool = True,
) -> FlexContinuationEligibility:
    """Fail closed unless the same failed action passes a fresh Flex-off check."""

    identity = _identity(failed_action)
    if identity is None:
        code: EligibilityReason = (
            "missing_failed_action"
            if failed_action is None
            else "invalid_failed_action"
        )
        return _result(code)
    common = {
        "action_id": identity.action_id,
        "receipt_id": identity.receipt_id,
        "work_id": identity.work_id,
        "document_revision": identity.document_revision,
        "selection_fingerprint": identity.selection_fingerprint,
    }
    if not isinstance(failed_preflight, Mapping):
        return _result("action_mismatch", **common)
    if (
        failed_preflight.get("work_id") != identity.work_id
        or failed_preflight.get("selection_fingerprint")
        != identity.selection_fingerprint
        or failed_preflight.get("action") != identity.action_kind
    ):
        return _result("action_mismatch", **common)

    checks = failed_preflight.get("checks")
    if not isinstance(checks, list):
        return _result("action_mismatch", **common)
    if (
        tuple(check.get("role") for check in checks if isinstance(check, Mapping))
        != identity.roles
    ):
        return _result("action_mismatch", **common)
    failed_revisions = {
        check.get("document_revision")
        for check in checks
        if isinstance(check, Mapping) and check.get("document_revision") is not None
    }
    if failed_revisions != {identity.document_revision}:
        return _result("action_mismatch", **common)
    failed = [
        check
        for check in checks
        if isinstance(check, Mapping) and check.get("outcome") != "supported"
    ]
    if not any(check.get("reason") == "flex_mode_not_supported" for check in failed):
        return _result("no_flex_rejection", **common)
    if any(check.get("classification") == "transient" for check in failed):
        return _result("transient_blocker", **common)
    deterministic = [
        check for check in failed if check.get("classification") == "deterministic"
    ]
    if any(check.get("reason") != "flex_mode_not_supported" for check in deterministic):
        return _result("mixed_deterministic_failures", **common)
    if len(deterministic) != len(failed):
        return _result("capability_blocker", **common)
    if not lifecycle_eligible:
        return _result("lifecycle_blocker", **common)
    if not approval_eligible:
        return _result("approval_blocker", **common)
    if disabled_preflight is None:
        return _result("inventory_not_fresh", **common)
    if (
        disabled_preflight.work_id != identity.work_id
        or disabled_preflight.selection_fingerprint != identity.selection_fingerprint
    ):
        return _result("selection_changed", **common)
    if tuple(check.role for check in disabled_preflight.checks) != identity.roles:
        return _result("selection_changed", **common)
    current_revisions = {
        check.result.document_revision
        for check in disabled_preflight.checks
        if check.result.document_revision is not None
    }
    if current_revisions != {identity.document_revision}:
        return _result("selection_changed", **common)
    freshness = disabled_preflight.inventory_freshness
    if freshness is None or freshness.from_cache or freshness.stale:
        return _result("inventory_not_fresh", **common)
    if not disabled_preflight.supported:
        code = _current_blocker(disabled_preflight)
        return _result(code, **common)
    if not disabled_preflight.checks or any(
        check.result.effective_flex_mode is not False
        for check in disabled_preflight.checks
    ):
        return _result("capability_blocker", **common)
    return _result("eligible", **common)


def _identity(value: Mapping[str, object] | None) -> OriginalActionIdentity | None:
    if value is None:
        return None
    try:
        return OriginalActionIdentity(**dict(value))  # type: ignore[arg-type]
    except (TypeError, ValueError, KeyError):
        return None


def _current_blocker(
    result: ProviderCapabilityBatchPreflight,
) -> EligibilityReason:
    failed = next(
        (check.result for check in result.checks if not check.result.supported), None
    )
    if failed is None:
        return "capability_blocker"
    if failed.classification == "transient":
        return "transient_blocker"
    if failed.reason in _CONFIGURATION_REASONS:
        return "configuration_blocker"
    if failed.reason in _PROVENANCE_REASONS:
        return "provenance_blocker"
    return "capability_blocker"


def _result(code: EligibilityReason, **identity: object) -> FlexContinuationEligibility:
    return FlexContinuationEligibility(
        code == "eligible", code, _MESSAGES[code], **identity
    )


__all__ = [
    "EligibilityReason",
    "FlexContinuationEligibility",
    "evaluate_flex_continuation_eligibility",
]
