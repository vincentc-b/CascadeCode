"""Task-budget admission and settlement at the physical provider boundary."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, replace
from typing import Any, Literal

from cascade.agent.errors import ProviderBudgetRefusedError
from cascade.agent.types import (
    IncidentProviderTurn,
    ProviderInvocationReceipt,
    ProviderTokenUsage,
    RoleResult,
    RoleTurn,
)
from cascade.agent.providers import ProviderId


@dataclass(frozen=True, slots=True)
class ProviderTurnAdmission:
    """One admitted durable operation and its local timing boundary."""

    budget: IncidentProviderTurn
    provider: ProviderId
    model_id: str
    invocation_id: str
    started: float


def provider_invocation_id(budget: IncidentProviderTurn) -> str:
    digest = hashlib.sha256(
        f"provider-invocation:{budget.incident_id}:{budget.operation_id}".encode()
    ).hexdigest()
    return f"sha256:{digest}"


def admit_provider_turn(
    turn: RoleTurn, *, provider: ProviderId
) -> ProviderTurnAdmission | None:
    """Reserve one paid turn and finite worst-case runtime before dispatch."""

    budget = turn.incident_turn
    if budget is None:
        if turn.recovery is not None and turn.recovery.outcome in {"resume", "safe_retry"}:
            raise ProviderBudgetRefusedError("owner_decision", "incident_budget_required")
        return None
    invocation_id = provider_invocation_id(budget)
    worst_case = {
        "paid_turns": 1,
        "model_seconds": budget.worst_case_model_seconds,
    }
    if budget.worst_case_known_tokens:
        worst_case["known_tokens"] = budget.worst_case_known_tokens
    # Keep the agent package importable during board/task package startup.
    from cascade.task.incident_budget import reserve_incident_operation

    decision = reserve_incident_operation(
        budget.incident_id,
        budget.operation_id,
        f"provider_turn:{provider}",
        worst_case,
        budget.claim_id,
        budget.policy_version,
        root=budget.root,
        attributes={
            "provider": provider,
            "model_id": turn.model_id,
            "invocation_id": invocation_id,
            "cancellation_bound": budget.cancellation_bound,
            "output_token_limit": budget.output_token_limit,
        },
    )
    if not decision.admitted:
        raise ProviderBudgetRefusedError(decision.state, decision.reason)
    return ProviderTurnAdmission(
        budget, provider, turn.model_id, invocation_id, time.monotonic()
    )


def _receipt(
    admission: ProviderTurnAdmission,
    *,
    outcome: Literal["success", "error", "interrupted", "unknown"],
    observed: ProviderInvocationReceipt | None,
) -> ProviderInvocationReceipt:
    usage = observed.usage if observed is not None else ProviderTokenUsage()
    invocation_id = (
        observed.invocation_id
        if observed is not None and observed.invocation_id
        else admission.invocation_id
    )
    return ProviderInvocationReceipt(
        provider=admission.provider,
        model_id=admission.model_id,
        invocation_id=invocation_id,
        usage=usage,
        outcome=outcome,
        cancellation_bound=admission.budget.cancellation_bound,
        output_token_limit=admission.budget.output_token_limit,
    )


def settle_provider_turn(
    admission: ProviderTurnAdmission,
    *,
    result: RoleResult | None = None,
    outcome: Literal["success", "error", "interrupted", "unknown"],
    failure_class: Literal["deterministic", "transient"] | None = None,
    provider_started: bool = True,
) -> ProviderInvocationReceipt:
    """Persist normalized evidence and charge the operation exactly once."""

    receipt = _receipt(
        admission,
        outcome=outcome,
        observed=result.invocation if result is not None else None,
    )
    elapsed = max(1, math.ceil(time.monotonic() - admission.started))
    qualities = (
        receipt.usage.input.quality,
        receipt.usage.output.quality,
        receipt.usage.cached_input.quality,
    )
    quality = (
        "unavailable"
        if "unavailable" in qualities
        else "estimated"
        if "estimated" in qualities
        else "known"
    )
    observation: dict[str, Any] = {
        "outcome": outcome,
        "quality": quality,
        "usage": {
            "paid_turns": 1 if provider_started else 0,
            "model_seconds": elapsed if provider_started else 0,
            "known_tokens": receipt.usage.known_total,
        },
        "invocation": receipt.to_dict(),
        "provider_started": provider_started,
    }
    if failure_class is not None:
        observation["failure_class"] = failure_class
    from cascade.task.incident_budget import settle_incident_operation

    settle_incident_operation(
        admission.budget.incident_id,
        admission.budget.operation_id,
        observation,
        root=admission.budget.root,
    )
    return receipt


def with_invocation(
    result: RoleResult, receipt: ProviderInvocationReceipt
) -> RoleResult:
    return replace(result, invocation=receipt)


__all__ = [
    "ProviderTurnAdmission",
    "admit_provider_turn",
    "provider_invocation_id",
    "settle_provider_turn",
    "with_invocation",
]
