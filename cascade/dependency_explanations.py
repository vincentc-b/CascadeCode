"""Human explanations for structured dependency outcomes and reasons.

These strings are presentation only.  Callers must continue to branch on the
stable outcome and reason codes from :mod:`cascade.dependency_evaluation`.
"""

from __future__ import annotations

from cascade.dependency_evaluation import DependencyOutcome, DependencyReason


_OUTCOME_EXPLANATIONS: dict[DependencyOutcome, str] = {
    "satisfied": "All declared dependencies are complete in canonical lifecycle state.",
    "dependency_unmet": (
        "One or more declared dependencies are not complete in canonical lifecycle state."
    ),
    "dependency_status_unavailable": (
        "Authoritative dependency status is unavailable; refresh before retrying."
    ),
}

_REASON_EXPLANATIONS: dict[DependencyReason, str] = {
    "dependency_incomplete": "The dependency has not completed.",
    "dependency_cancelled": "The dependency was cancelled.",
    "dependency_status_column_mismatch": (
        "The dependency status and canonical board column do not agree."
    ),
    "dependency_not_found": "The dependency is absent from the authoritative board.",
    "dependency_source_unavailable": (
        "The authoritative dependency source could not be read."
    ),
}


def dependency_outcome_explanation(outcome: DependencyOutcome) -> str:
    """Return presentation text without changing the machine outcome."""

    return _OUTCOME_EXPLANATIONS[outcome]


def dependency_reason_explanation(reason: DependencyReason | None) -> str | None:
    """Return presentation text for a stable row reason, when one exists."""

    return _REASON_EXPLANATIONS[reason] if reason is not None else None
