"""Serialized, non-destructive recovery for orphaned Task delivery.

The health sweep deliberately only observes.  This module is the one place
allowed to turn an observation into a queue replay or a resumed Task run.  It
re-reads every mutable input while holding the board lifecycle lock, so a stale
sweep observation and concurrent callers cannot steal a live task.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Literal

from cascade.board.context import resolve_root
from cascade.board.store import read_doc
from cascade.task.orphan_delivery import (
    OrphanDeliveryIncident,
    PinnedExecutionInputs,
    derive_orphan_delivery_incident,
    snapshot_orphan_delivery_state,
)
from cascade.task.lifecycle_lock import lifecycle_root, task_lifecycle_lock
from cascade.watchdog.incidents import (
    authoritative_generation,
    incident_record,
    project_incident,
)

RecoveryDecision = Literal[
    "no_op_live_owner",
    "already_delivered",
    "requeue_commit",
    "resume_workspace",
    "defer_draining",
    "unsafe",
]


@dataclass(frozen=True)
class RecoveryResult:
    """Durable outcome of one logical orphan-delivery incident."""

    incident_id: str
    decision: RecoveryDecision
    reason: str
    mutated: bool
    attempt: int | None = None
    diagnostics: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def recover_orphan_delivery(
    task_id: str,
    *,
    root: Path,
    observed_incident: str | None = None,
    feature_id: str | None = None,
    kickoff: Callable[[str, Path, str | None], None] | None = None,
) -> RecoveryResult:
    """Recover one abandoned Task delivery, or return its prior durable result.

    ``observed_incident`` is only an idempotency hint from a health sweep.  It
    never authorizes recovery: current ownership, cancellation, validation,
    Git, and checkpoint facts are all read again under ``process_lock``.
    """

    repo = resolve_root(root)
    resume: tuple[str, str | None] | None = None
    with task_lifecycle_lock(root=repo):
        task = read_doc(task_id, root=repo)
        attempt = _execution_attempt(task_id, repo)
        incident_id = observed_incident or _incident_id(task_id, attempt)
        ledger = _read_ledger(repo)
        facts: dict[str, object] = {
            "status": task.meta.status,
            "parent": task.meta.parent,
            "document_revision": task.sha,
        }
        generation: str | None = None

        # An audit admission pins the typed owning Feature. Recheck that exact
        # identity under the same lock as every delivery mutation; a document
        # revision or Git SHA is evidence, never a substitute for ownership.
        if feature_id is not None and task.meta.parent != feature_id:
            result = _result(
                incident_id, "unsafe", "task_feature_owner_changed", attempt
            )
        # Do not enqueue while the worker is draining, or while cancellation
        # owns the lifecycle transition.  Neither condition is recoverable by
        # retrying this operation in the same process.
        elif task.meta.status == "cancelling":
            result = _result(
                incident_id, "defer_draining", "cancellation_in_progress", attempt
            )
        else:
            from cascade.workspace.drain import is_draining

            if is_draining():
                result = _result(
                    incident_id, "defer_draining", "worker_draining", attempt
                )
            else:
                state = snapshot_orphan_delivery_state(
                    task_id,
                    root=repo,
                    pinned_inputs=_pinned_inputs(task_id, task.meta.parent, repo),
                )
                from cascade.task_rollup import _merge_head_pair

                heads = _merge_head_pair(task_id, repo)
                facts = {
                    "state": asdict(state),
                    "heads": list(heads) if heads else None,
                    "status": task.meta.status,
                    "parent": task.meta.parent,
                    "document_revision": task.sha,
                }
                generation = authoritative_generation(
                    work_id=task_id,
                    tier="task",
                    evidence=facts,
                    capability="supervisor_recover_task_delivery",
                )
                # Observations are hints, never authorization or cache identity.
                incident_id = f"{_incident_id(task_id, attempt)}:{generation[-24:]}"
                previous_row = ledger.get(incident_id)
                previous = _result_from_row(previous_row)
                if (
                    previous is not None
                    and isinstance(previous_row, dict)
                    and isinstance(previous_row.get("incident"), dict)
                    and project_incident(
                        generation, {incident_id: previous_row}
                    ).eligible
                ):
                    previous = None
                if previous is not None:
                    from cascade.task.execution import execution_view

                    execution = execution_view(task_id, root=repo) or {}
                    if (
                        previous.decision != "resume_workspace"
                        or execution.get("health") != "stale"
                    ):
                        return previous
                    # A persisted handoff with no live owner is replayable after
                    # the queue reservation expires (including supervisor exit).
                    result = previous
                    resume = (task_id, task.meta.parent)
                    from cascade.task.execution import mark_stall_recovery_queued

                    mark_stall_recovery_queued(task_id, root=repo)
                else:
                    incident = derive_orphan_delivery_incident(state)
                    result, resume = _apply_incident(
                        incident,
                        incident_id,
                        attempt,
                        repo,
                        feature_id=task.meta.parent,
                    )
                    result = replace(
                        result,
                        diagnostics={
                            **(result.diagnostics or {}),
                            "generation": generation,
                            "observation": facts,
                        },
                    )

        if generation is None:
            generation = authoritative_generation(
                work_id=task_id,
                tier="task",
                evidence=facts,
                capability="supervisor_recover_task_delivery",
            )
            incident_id = f"{_incident_id(task_id, attempt)}:{generation[-24:]}"
            result = replace(
                result,
                incident_id=incident_id,
                diagnostics={
                    **(result.diagnostics or {}),
                    "generation": generation,
                    "observation": facts,
                },
            )
        ledger[incident_id] = _ledger_row(
            result,
            task_id=task_id,
            owner=(
                f"feature:{task.meta.parent}" if task.meta.parent else f"task:{task_id}"
            ),
            generation=generation,
            evidence=facts,
            prior=ledger.get(incident_id),
        )
        if resume is not None:
            # The queued transition is our own handoff, not a new external
            # generation. Reserve its resulting observation before unlocking.
            queued_facts = {
                **facts,
                "state": {**facts["state"], "execution_phase": "queued"},
            }
            queued_generation = authoritative_generation(
                work_id=task_id,
                tier="task",
                evidence=queued_facts,
                capability="supervisor_recover_task_delivery",
            )
            queued_id = (
                f"{_incident_id(task_id, result.attempt)}:{queued_generation[-24:]}"
            )
            ledger[queued_id] = _ledger_row(
                result,
                task_id=task_id,
                owner=(
                    f"feature:{task.meta.parent}"
                    if task.meta.parent
                    else f"task:{task_id}"
                ),
                generation=queued_generation,
                evidence=queued_facts,
                prior=ledger.get(queued_id),
            )
        _write_ledger(repo, ledger)

    # Starting a model turn while the lifecycle lock is held invites lock
    # inversion.  The durable queued marker above makes this handoff replayable
    # if the supervisor exits between unlock and kickoff.
    if resume is not None:
        _kickoff(task_id, repo, resume[1], kickoff)
    return result


def supervisor_recover_task_delivery(
    task_id: str,
    *,
    root: Path,
    observed_incident: str | None = None,
    feature_id: str | None = None,
) -> RecoveryResult:
    """Named shared-supervisor entry point (kept small for health callers)."""

    return recover_orphan_delivery(
        task_id,
        root=root,
        observed_incident=observed_incident,
        feature_id=feature_id,
    )


def recovery_incident(task_id: str, *, root: Path) -> RecoveryResult | None:
    """Return the durable result for the Task's current recovery attempt.

    This is intentionally read-only so the War Room can show the same
    incident that the supervisor and Feature Team share without offering a
    second recovery path.
    """

    repo = resolve_root(root)
    ledger = _read_ledger(repo)
    current = _result_from_row(
        ledger.get(_incident_id(task_id, _execution_attempt(task_id, repo)))
    )
    if current is not None:
        return current
    # A resumed execution advances its attempt after recording the incident
    # that triggered it.  Keep that incident visible until a later attempt
    # records its own decision.
    prefix = f"{task_id}:delivery:"
    candidates = [
        result
        for incident_id, row in ledger.items()
        if incident_id.startswith(prefix)
        and (result := _result_from_row(row)) is not None
    ]
    latest = candidates[-1] if candidates else None
    if latest is not None and latest.reason == "validated_delivery_already_queued":
        from cascade.task_rollup import pending_task_merges

        if task_id not in pending_task_merges(repo):
            return _result(
                latest.incident_id,
                "unsafe",
                "delivery_invalidated_revalidation_pending",
                latest.attempt,
            )
    return latest


def _incident_sort_key(result: RecoveryResult) -> tuple[int, str]:
    """Order numeric attempts naturally while retaining legacy unknown ids."""

    suffix = result.incident_id.rsplit(":", 1)[-1]
    try:
        return int(suffix), result.incident_id
    except ValueError:
        return -1, result.incident_id


def _apply_incident(
    incident: OrphanDeliveryIncident,
    incident_id: str,
    attempt: int | None,
    repo: Path,
    *,
    feature_id: str | None,
) -> tuple[RecoveryResult, tuple[str, str | None] | None]:
    if incident.outcome == "live_owner":
        return _result(incident_id, "no_op_live_owner", incident.reason, attempt), None
    if incident.outcome == "noop_replay":
        return _result(incident_id, "already_delivered", incident.reason, attempt), None
    if incident.outcome == "unsafe_or_missing_state":
        return _result(incident_id, "unsafe", incident.reason, attempt, incident), None

    # Both mutating paths first attach to the *existing* registration.  This
    # deliberately refuses to create, fast-forward, clean, reset, or replace a
    # worktree; dirty state remains untouched.
    from cascade.task.worktree import attach_active_task_run

    run = attach_active_task_run(incident.task_id, root=repo)
    if run is None:
        return _result(
            incident_id, "unsafe", "task_workspace_not_attachable", attempt, incident
        ), None

    if incident.outcome == "requeue_validated_commit":
        from cascade.task.wiring import enqueue_validated_delivery

        if not enqueue_validated_delivery(incident.task_id, root=repo):
            return _result(
                incident_id,
                "unsafe",
                "validated_delivery_recheck_failed",
                attempt,
                incident,
            ), None
        return _result(
            incident_id, "requeue_commit", incident.reason, attempt, mutated=True
        ), None

    if incident.outcome == "resume_execution":
        from cascade.task.execution import mark_stall_recovery_queued

        row = mark_stall_recovery_queued(incident.task_id, root=repo)
        return (
            _result(
                incident_id,
                "resume_workspace",
                incident.reason,
                _optional_int(row.get("attempt")),
                mutated=True,
            ),
            (incident.task_id, feature_id),
        )
    return _result(
        incident_id, "unsafe", "unknown_recovery_outcome", attempt, incident
    ), None


def _pinned_inputs(
    task_id: str, feature_id: str | None, root: Path
) -> PinnedExecutionInputs | None:
    """Read pins from the existing checkpoint without initializing new state."""

    from cascade.task.checkpoint import checkpoint_path

    if not checkpoint_path(task_id, root=root).is_file():
        return None
    from cascade.workspace.kickoff import _graph_state

    state = _graph_state(task_id, "task", root=root, feature_id=feature_id) or {}
    providers = state.get("provider_ids") or {}
    models = state.get("model_ids") or {}
    reasoning = state.get("reasoning_ids") or {}
    flex = state.get("flex_modes") or {}
    return PinnedExecutionInputs(
        provider_id=_optional_str(providers.get("swe")),
        model_id=_optional_str(models.get("swe")),
        reasoning_level=_optional_str(reasoning.get("swe")),
        flex_mode=flex.get("swe") if isinstance(flex.get("swe"), bool) else None,
    )


def _kickoff(
    task_id: str,
    root: Path,
    feature_id: str | None,
    callback: Callable[[str, Path, str | None], None] | None,
) -> None:
    if callback is not None:
        callback(task_id, root, feature_id)
        return
    from cascade.workspace.kickoff import kickoff_turn
    from cascade.workspace.types import KickoffReason

    kickoff_turn(
        KickoffReason("queue_event", task_id, "watchdog", root, feature_id=feature_id)
    )


def _execution_attempt(task_id: str, root: Path) -> int | None:
    from cascade.task.execution import execution_view

    view = execution_view(task_id, root=root) or {}
    return _optional_int(view.get("attempt"))


def _incident_id(task_id: str, attempt: int | None) -> str:
    return f"{task_id}:delivery:{attempt if attempt is not None else 'unknown'}"


def _result(
    incident_id: str,
    decision: RecoveryDecision,
    reason: str,
    attempt: int | None,
    incident: OrphanDeliveryIncident | None = None,
    *,
    mutated: bool = False,
) -> RecoveryResult:
    diagnostics: dict[str, object] | None = None
    if incident is not None:
        diagnostics = {
            "outcome": incident.outcome,
            "reason": incident.reason,
            "worktree_dirty": incident.state.git.worktree_dirty,
        }
    return RecoveryResult(incident_id, decision, reason, mutated, attempt, diagnostics)


def _ledger_path(root: Path) -> Path:
    return lifecycle_root(root) / ".cascade" / "orphan_delivery_recoveries.json"


def _read_ledger(root: Path) -> dict[str, dict[str, object]]:
    path = _ledger_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("recoveries") if isinstance(payload, dict) else None
    return (
        {
            str(key): dict(value)
            for key, value in rows.items()
            if isinstance(value, dict)
        }
        if isinstance(rows, dict)
        else {}
    )


def _write_ledger(root: Path, ledger: dict[str, dict[str, object]]) -> None:
    path = _ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {"version": 1, "recoveries": ledger}, handle, indent=2, sort_keys=False
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def _result_from_row(row: dict[str, object] | None) -> RecoveryResult | None:
    if row is None:
        return None
    decision = row.get("decision")
    incident_id = row.get("incident_id")
    reason = row.get("reason")
    if (
        not isinstance(decision, str)
        or not isinstance(incident_id, str)
        or not isinstance(reason, str)
    ):
        return None
    if decision not in {
        "no_op_live_owner",
        "already_delivered",
        "requeue_commit",
        "resume_workspace",
        "defer_draining",
        "unsafe",
    }:
        return None
    return RecoveryResult(
        incident_id,
        decision,
        reason,
        bool(row.get("mutated")),
        _optional_int(row.get("attempt")),
        dict(row["diagnostics"]) if isinstance(row.get("diagnostics"), dict) else None,
    )  # type: ignore[arg-type]


def _ledger_row(
    result: RecoveryResult,
    *,
    task_id: str,
    owner: str,
    generation: str,
    evidence: dict[str, object],
    prior: dict[str, object] | None,
) -> dict[str, object]:
    row = result.as_dict()
    prior_contract = prior.get("incident") if isinstance(prior, dict) else None
    attempts = (
        list(prior_contract.get("attempts") or [])
        if isinstance(prior_contract, dict)
        else []
    )
    attempts.append(
        {
            "attempt": result.attempt,
            "decision": result.decision,
            "reason": result.reason,
        }
    )
    if result.decision == "requeue_commit":
        outcome = "success"
    elif result.decision == "resume_workspace":
        outcome = "claimed"
    elif result.decision == "unsafe":
        outcome = "unsafe"
    elif result.decision == "defer_draining":
        outcome = "deferred"
    else:
        outcome = "no_op"
    row["incident"] = incident_record(
        work_id=task_id,
        tier="task",
        accountable_owner=owner,
        failure_class=result.reason,
        generation=generation,
        evidence=evidence,
        selected_capability="supervisor_recover_task_delivery",
        request={"incident_id": result.incident_id},
        acknowledgement={"decision": result.decision},
        result={"reason": result.reason, "mutated": result.mutated},
        attempts=attempts,
        outcome=outcome,  # type: ignore[arg-type]
    )
    return row


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


__all__ = [
    "RecoveryDecision",
    "RecoveryResult",
    "recover_orphan_delivery",
    "recovery_incident",
    "supervisor_recover_task_delivery",
]
