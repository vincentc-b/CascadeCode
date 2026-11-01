"""Read-only model for recovering an interrupted Task delivery.

The supervisor and the direct-report health sweep both need to answer the
same question after a worker disappears.  This module deliberately does not
start a turn, update a queue, or alter git state: it turns one coherent
snapshot, taken while the Task lifecycle lock is held, into a stable incident
and a single next action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.context import resolve_root
from cascade.board.gitutil import _run
from cascade.board.store import read_doc
from cascade.task.checkpoint import checkpoint_path
from cascade.watchdog.lock import process_lock

RecoveryOutcome = Literal[
    "live_owner",
    "requeue_validated_commit",
    "resume_execution",
    "unsafe_or_missing_state",
    "noop_replay",
]


@dataclass(frozen=True)
class PinnedExecutionInputs:
    """The provider settings required to replay the same SWE execution."""

    provider_id: str | None
    model_id: str | None
    reasoning_level: str | None = None
    flex_mode: bool | None = None

    @property
    def complete(self) -> bool:
        return bool(self.provider_id and self.model_id)


@dataclass(frozen=True)
class DeliveryEvidence:
    """Durable final-validation identity and whether it still matches refs."""

    deliverable_sha: str | None = None
    feature_base_sha: str | None = None
    current: bool = False
    queued: bool = False

    @property
    def complete(self) -> bool:
        return bool(self.deliverable_sha and self.feature_base_sha)


@dataclass(frozen=True)
class TaskGitState:
    """Only the git facts relevant to a non-destructive recovery decision."""

    branch_exists: bool
    worktree_exists: bool
    worktree_on_branch: bool
    worktree_dirty: bool = False

    @property
    def resumable(self) -> bool:
        # Dirty state is intentionally safe: recovery must preserve it.
        return self.branch_exists and self.worktree_exists and self.worktree_on_branch


@dataclass(frozen=True)
class OrphanDeliveryState:
    """All facts used to derive one Task orphan-delivery decision.

    This is intentionally value-only.  It makes decisions replayable across a
    supervisor restart and lets callers re-check every fact under their lock
    immediately before carrying out the selected action.
    """

    task_id: str
    task_active: bool
    owner_live: bool
    execution_phase: str | None
    checkpoint_present: bool
    pinned_inputs: PinnedExecutionInputs | None
    delivery: DeliveryEvidence
    git: TaskGitState


@dataclass(frozen=True)
class OrphanDeliveryIncident:
    task_id: str
    outcome: RecoveryOutcome
    reason: str
    state: OrphanDeliveryState

    @property
    def recoverable(self) -> bool:
        return self.outcome in {"requeue_validated_commit", "resume_execution"}


def derive_orphan_delivery_incident(state: OrphanDeliveryState) -> OrphanDeliveryIncident:
    """Derive the one safe next action, without modifying external state.

    Ordering is deliberate.  A fresh owner always wins; a durable delivery
    handoff wins over a model replay; and any missing or contradictory state
    is refused before considering a resume.  Replaying an already-published
    queue entry is a no-op, rather than a second recovery action.
    """

    if not state.task_active or state.execution_phase == "terminal":
        return _incident(state, "noop_replay", "task_not_recoverable")
    if state.owner_live:
        return _incident(state, "live_owner", "execution_lease_live")
    if state.delivery.queued and state.delivery.complete and state.delivery.current:
        return _incident(state, "noop_replay", "validated_delivery_already_queued")
    if state.delivery.complete and state.delivery.current:
        return _incident(state, "requeue_validated_commit", "validated_delivery_matches_git")
    if state.delivery.complete and not state.delivery.current:
        return _incident(state, "unsafe_or_missing_state", "validated_delivery_no_longer_matches_git")
    if not state.git.resumable:
        return _incident(state, "unsafe_or_missing_state", "task_branch_or_worktree_missing")
    if not state.checkpoint_present:
        return _incident(state, "unsafe_or_missing_state", "task_checkpoint_missing")
    if state.pinned_inputs is None or not state.pinned_inputs.complete:
        return _incident(state, "unsafe_or_missing_state", "pinned_execution_inputs_missing")
    if state.execution_phase not in {"queued", "running"}:
        return _incident(state, "noop_replay", "no_resumable_execution")
    return _incident(state, "resume_execution", "orphaned_execution_resumable")


def _incident(
    state: OrphanDeliveryState, outcome: RecoveryOutcome, reason: str
) -> OrphanDeliveryIncident:
    return OrphanDeliveryIncident(state.task_id, outcome, reason, state)


def snapshot_orphan_delivery_state(
    task_id: str,
    *,
    root: Path,
    pinned_inputs: PinnedExecutionInputs | None = None,
) -> OrphanDeliveryState:
    """Collect stable recovery facts while holding the shared lifecycle lock.

    ``pinned_inputs`` is supplied by the checkpoint reader/turn owner.  The
    model never opens or initializes a checkpoint merely to inspect it; a
    missing pin is therefore safely represented as unavailable rather than
    manufacturing execution state during an observation.
    """

    repo = resolve_root(root)
    with process_lock:
        task = read_doc(task_id, root=repo)
        from cascade.task.execution import execution_lease_is_live, execution_view
        from cascade.task_rollup import (
            delivery_evidence_is_current,
            pending_task_merges,
            queued_delivery_evidence,
        )
        from cascade.workspace.integration_worktree import get_integration_worktree, integration_branch

        execution = execution_view(task_id, root=repo) or {}
        evidence = queued_delivery_evidence(task_id, root=repo)
        branch = integration_branch("task", task_id)
        branch_exists = _ref_exists(repo, branch)
        checkout = get_integration_worktree(repo, "task", task_id)
        worktree_exists = checkout is not None and checkout.path.is_dir()
        on_branch = worktree_exists and checkout is not None and _worktree_on_branch(checkout.path, branch)
        delivery = DeliveryEvidence(
            deliverable_sha=(evidence or {}).get("deliverable_sha"),
            feature_base_sha=(evidence or {}).get("feature_base_sha"),
            current=bool(evidence and delivery_evidence_is_current(task_id, evidence, root=repo)),
            queued=task_id in pending_task_merges(repo),
        )
        return OrphanDeliveryState(
            task_id=task_id,
            task_active=task.meta.tier == "task" and task.meta.status == "active",
            owner_live=execution_lease_is_live(task_id, root=repo),
            execution_phase=execution.get("phase") if isinstance(execution.get("phase"), str) else None,
            checkpoint_present=checkpoint_path(task_id, root=repo).is_file(),
            pinned_inputs=pinned_inputs,
            delivery=delivery,
            git=TaskGitState(
                branch_exists=branch_exists,
                worktree_exists=worktree_exists,
                worktree_on_branch=on_branch,
                worktree_dirty=bool(worktree_exists and checkout is not None and _worktree_dirty(checkout.path)),
            ),
        )


def _ref_exists(root: Path, ref: str) -> bool:
    return _run(["rev-parse", "--verify", f"{ref}^{{commit}}"], root, check=False).returncode == 0


def _worktree_on_branch(worktree: Path, branch: str) -> bool:
    result = _run(["branch", "--show-current"], worktree, check=False)
    return result.returncode == 0 and result.stdout.strip() == branch


def _worktree_dirty(worktree: Path) -> bool:
    result = _run(["status", "--porcelain"], worktree, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())
