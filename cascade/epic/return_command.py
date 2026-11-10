"""Human-authorized boundary for a durable Epic graph return to backlog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cascade.board.context import resolve_root
from cascade.board.errors import BoardError
from cascade.epic.return_eligibility import (
    ReturnEligibility,
    ReturnEligibilityInput,
    ReturnEligibilityReasonCode,
    ReturnEligibilityRefusal,
    evaluate_return_eligibility,
)
from cascade.epic.lifecycle_gate import LifecycleGate, lifecycle_gate

Actor = Literal["human", "agent", "system"]
SnapshotLoader = Callable[[str], ReturnEligibilityInput]
TransitionCapability = Callable[[str, str], object]


@dataclass(frozen=True, slots=True)
class ReturnEpicCommandResult:
    """Stable response shape for API callers; refusals never mutate state."""

    ok: bool
    epic_id: str
    request_id: str
    eligibility: ReturnEligibility | None = None
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "epic_id": self.epic_id,
            "request_id": self.request_id,
        }
        if self.eligibility is not None:
            eligibility = self.eligibility.to_dict()
            payload["eligibility"] = eligibility
            # Keep the stable list convenient for simple command consumers.
            payload["refusals"] = eligibility["refusals"]
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        if self.message is not None:
            payload["message"] = self.message
        return payload


def return_epic_to_backlog(
    epic_id: str,
    request_id: str,
    *,
    actor: Actor = "system",
    snapshot_loader: SnapshotLoader | None = None,
    transition: TransitionCapability | None = None,
    gate: LifecycleGate | None = None,
    quiesce_timeout: float = 0.0,
    root: Path | None = None,
) -> ReturnEpicCommandResult:
    """Return a graph through production persistence or an injected test adapter.

    Injected snapshots still require an explicit transition capability; the
    default path discovers and preserves the complete live graph itself.
    """

    if not isinstance(epic_id, str) or not epic_id.strip():
        return _error("", request_id, "invalid_epic_id", "An Epic ID is required.")
    if not isinstance(request_id, str) or not request_id.strip():
        return _error(epic_id, "", "invalid_request_id", "A request ID is required.")
    if actor != "human":
        return _error(
            epic_id, request_id, "unauthorized", "A human authorization is required."
        )

    if snapshot_loader is None and transition is None:
        from cascade.epic.return_graph import execute_return
        from cascade.epic.return_transaction import TransitionUnsafe

        try:
            return execute_return(
                epic_id,
                request_id,
                root=resolve_root(root),
                gate=gate,
                timeout=quiesce_timeout,
            )
        except (BoardError, OSError, ValueError, KeyError, TransitionUnsafe):
            return _error(
                epic_id,
                request_id,
                "return_state_unavailable",
                "Return state could not be preserved; retry or inspect the transition journal.",
            )

    loader = snapshot_loader or (
        lambda item_id: load_return_eligibility_snapshot(item_id, root=root)
    )
    try:
        snapshot = loader(epic_id)
        eligibility = evaluate_return_eligibility(snapshot)
    except (BoardError, OSError, ValueError, KeyError):
        # Required state that cannot be read must fail closed, and must not
        # leak filesystem or provider details to the operator.
        eligibility = evaluate_return_eligibility(_unreadable_snapshot(epic_id))
    if not eligibility.eligible:
        return ReturnEpicCommandResult(
            False, epic_id, request_id, eligibility=eligibility
        )
    if transition is None:
        return _error(
            epic_id,
            request_id,
            "transition_unavailable",
            "The durable return transition is not available yet; no changes were made.",
            eligibility=eligibility,
        )
    member_ids = tuple(member.id for member in snapshot.graph or () if member.id)
    with (gate or lifecycle_gate()).transition(
        epic_id, member_ids, timeout=quiesce_timeout
    ) as quiesced:
        # Read again only after admission is closed and while the per-Epic
        # lifecycle lock is held.  A stale UI/pre-lock observation can never
        # authorize a mutation.
        eligibility = _load_eligibility(loader, epic_id)
        if not quiesced:
            return ReturnEpicCommandResult(
                False,
                epic_id,
                request_id,
                eligibility=_quiescence_refusal(eligibility),
            )
        if not eligibility.eligible:
            return ReturnEpicCommandResult(
                False, epic_id, request_id, eligibility=eligibility
            )
        transition(epic_id, request_id)
        return ReturnEpicCommandResult(
            True, epic_id, request_id, eligibility=eligibility
        )


def load_return_eligibility_snapshot(
    epic_id: str, *, root: Path | None = None
) -> ReturnEligibilityInput:
    """Read the same authoritative graph facts used by the production command."""
    from cascade.epic.return_graph import load_snapshot

    return load_snapshot(epic_id, root=resolve_root(root))


def _unreadable_snapshot(epic_id: str) -> ReturnEligibilityInput:
    return ReturnEligibilityInput(
        epic_id=epic_id,
        epic_tier=None,
        epic_status=None,
        epic_transition_in_progress=None,
        graph=None,
        graph_complete=None,
        source_brief_revision=None,
        lock_order=None,
        conflicting_lifecycle_operation=None,
    )


def _load_eligibility(loader: SnapshotLoader, epic_id: str) -> ReturnEligibility:
    try:
        return evaluate_return_eligibility(loader(epic_id))
    except (BoardError, OSError, ValueError, KeyError):
        return evaluate_return_eligibility(_unreadable_snapshot(epic_id))


def _quiescence_refusal(eligibility: ReturnEligibility) -> ReturnEligibility:
    if ReturnEligibilityReasonCode.TURN_NOT_QUIESCED.value in eligibility.reason_codes:
        return eligibility
    refusal = ReturnEligibilityRefusal(
        code=ReturnEligibilityReasonCode.TURN_NOT_QUIESCED,
        message="One or more graph members still have an unquiesced or unknown turn.",
    )
    return ReturnEligibility(eligible=False, refusals=(*eligibility.refusals, refusal))


def _error(
    epic_id: str,
    request_id: str,
    code: str,
    message: str,
    *,
    eligibility: ReturnEligibility | None = None,
) -> ReturnEpicCommandResult:
    return ReturnEpicCommandResult(
        False,
        epic_id,
        request_id,
        eligibility=eligibility,
        error_code=code,
        message=message,
    )
