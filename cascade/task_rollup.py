"""Durable retry queue for automatic task-to-feature merges."""

from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TypedDict

from cascade.task.lifecycle_lock import lifecycle_root
from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.gitutil import _run
from cascade.board.store import read_doc
from cascade.task.action_recovery import (
    ActionRecoveryError,
    ActionResult,
    create_or_load_action,
    load_action,
    record_owner_decision,
    record_owner_resolution,
    replace_action_metadata,
    resume_action,
)
from cascade.task.execution import mark_merge_blocked
from cascade.watchdog.events import append_event
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event


_QUEUED_MERGE_KIND = "queued_task_merge"
# The legacy queue retried indefinitely.  Keep recovery durable without making a
# short-lived transient refusal terminal during normal supervisor operation.
_QUEUED_MERGE_ATTEMPT_BOUND = 100
_SEMANTIC_CONFLICT_OWNERS = {
    "task_code": "task_team",
    "cross_feature": "epic_team",
    "epic_contract": "epic_team",
}


class ParentLifecycleMismatch(TypedDict):
    """Typed envelope joining one queued delivery to Feature repair evidence."""

    schema_version: int
    failure_class: str
    authoritative_generation: str
    accountable_owner: str
    selected_operation: str
    evidence: dict[str, Any]


def _path(root: Path) -> Path:
    return lifecycle_root(root) / ".cascade" / "pending-task-merges.json"


def _read(root: Path) -> list[str]:
    path = _path(root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(item) for item in raw if isinstance(item, str)] if isinstance(raw, list) else []


def _write(root: Path, task_ids: list[str]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(sorted(set(task_ids)), indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _queued_merge_action_id(task_id: str) -> str:
    """Return the stable recovery identity for one legacy queue entry."""

    return f"{task_id}:queued_merge"


def _queued_merge_action(
    task_id: str, root: Path, *, delivery_evidence: dict[str, str] | None = None
) -> dict:
    """Create the durable queue record for a validated delivery.

    The recovery action is the authoritative queue entry.  Keep the legacy
    list below as a cheap scheduling index, but put the validation identity on
    the durable action so a task id alone can never be mistaken for a
    different deliverable.
    """

    metadata: dict[str, object] = {"task_id": task_id}
    if delivery_evidence is not None:
        metadata["final_validation"] = dict(delivery_evidence)
        repair_link = _feature_repair_delivery_link(task_id, root)
        if repair_link is not None:
            metadata["feature_repair"] = repair_link
    action = create_or_load_action(
        _queued_merge_action_id(task_id),
        _QUEUED_MERGE_KIND,
        root=root,
        attempt_bound=_QUEUED_MERGE_ATTEMPT_BOUND,
        metadata=metadata,
    )
    # A repaired task may validate a newly amended deliverable or a rebased
    # Feature base.  Keep one queue identity (and therefore one scheduled
    # merge) but make its persisted validation evidence describe the latest
    # green validation.
    if delivery_evidence is not None and action.get("metadata") != metadata:
        action = replace_action_metadata(
            _queued_merge_action_id(task_id), metadata, root=root
        )
    if delivery_evidence is not None and delivery_evidence_is_current(task_id, delivery_evidence, root=root):
        from cascade.task.action_recovery import rearm_validated_task_action
        action = rearm_validated_task_action(task_id, delivery_evidence, root=root)
        for decision in action.get("owner_decisions", []):
            if decision.get("state") == "awaiting_resolution":
                action = record_owner_resolution(
                    action["action_id"], decision["decision_id"],
                    f"validated:{delivery_evidence['deliverable_sha']}:{delivery_evidence['feature_base_sha']}",
                    root=root, metadata={"final_validation": delivery_evidence},
                )
        # Queue publication must not commit parent metadata: moving the Feature
        # head here invalidates the exact pair that just passed validation.
        # Reconcile derived blockers only after the canonical merge succeeds.
    return action


def _feature_repair_delivery_link(
    task_id: str, root: Path
) -> dict[str, object] | None:
    """Bind current queue evidence to the repair generation that owns the Task."""

    try:
        feature_id = read_doc(task_id, root=root).meta.parent
    except NotFound:
        return None
    if not feature_id:
        return None
    from cascade.feature.repair import current_feature_repair_record

    repair = current_feature_repair_record(feature_id, root=root)
    if repair is None or (
        repair.get("task_id") != task_id
        and repair.get("request_id") != _queued_merge_action_id(task_id)
    ):
        return None
    action_id = repair.get("action_id")
    generation = repair.get("generation")
    if not isinstance(action_id, str) or not isinstance(generation, int):
        return None
    return {
        "action_id": action_id,
        "generation": generation,
        "feature_id": feature_id,
    }


def queue_task_merge(
    task_id: str,
    *,
    root: Path,
    delivery_evidence: dict[str, str] | None = None,
) -> None:
    repo = resolve_root(root)
    # Persist the evidence-bearing recovery action before publishing the
    # scheduling index.  Callers do not expose a ready state until this
    # function returns, so an interruption can leave an unadvertised action
    # but can never leave an advertised delivery without its queue record.
    # Existing queue files remain a plain list for compatibility.
    _queued_merge_action(task_id, repo, delivery_evidence=delivery_evidence)
    if delivery_evidence is not None:
        from cascade.feature.repair import mark_feature_repair_delivery_pending

        mark_feature_repair_delivery_pending(
            task_id, delivery_evidence, root=repo
        )
    with process_lock:
        pending = _read(repo)
        if task_id not in pending:
            pending.append(task_id)
            _write(repo, pending)


def queued_delivery_evidence(task_id: str, *, root: Path) -> dict[str, str] | None:
    """Return the exact green validation attached to a queued delivery."""

    action = load_action(_queued_merge_action_id(task_id), root=resolve_root(root))
    metadata = action.get("metadata") if action is not None else None
    evidence = metadata.get("final_validation") if isinstance(metadata, dict) else None
    if not isinstance(evidence, dict) or set(evidence) != {
        "task_id", "deliverable_sha", "feature_base_sha"
    }:
        return None
    if not all(isinstance(value, str) and value for value in evidence.values()):
        return None
    return dict(evidence)


def delivery_evidence_is_current(
    task_id: str, evidence: dict[str, str], *, root: Path
) -> bool:
    """Whether evidence still names the current, unmodified delivery snapshot."""

    from cascade.task.worktree import task_worktree_has_changes

    heads = _merge_head_pair(task_id, resolve_root(root))
    return (
        heads is not None
        and not task_worktree_has_changes(task_id, root=root)
        and evidence == {
            "task_id": task_id,
            "deliverable_sha": heads[0],
            "feature_base_sha": heads[1],
        }
    )


def defer_uncommitted_delivery(task_id: str, *, root: Path) -> None:
    """Return later source edits to the same Task without spending merge attempts."""

    from cascade.task.execution import (
        execution_view,
        mark_stall_recovery_queued,
        record_running_error,
    )
    from cascade.task.lifecycle_lock import task_lifecycle_lock
    from cascade.task.wiring import invalidate_validated_delivery

    with task_lifecycle_lock(root=root):
        invalidate_validated_delivery(task_id, root=root)
        execution = execution_view(task_id, root=root) or {}
        if (
            execution.get("phase") == "queued"
            and execution.get("last_error") == "uncommitted_delivery"
        ):
            return
        # Append before the queued marker so an interrupted transition remains
        # discoverable through the ordinary durable Task input path.
        append_event(
            task_id,
            Event(
                type="TaskValidationRetryRequested",
                ts=datetime.now(timezone.utc),
                payload={
                    "task_id": task_id,
                    "reason": "uncommitted_delivery",
                    "instruction": (
                        "Later edits remain outside the validated commit. Preserve them, "
                        "finish the existing Task, commit, then rerun supervised tests "
                        "on the clean committed tree before delivery."
                    ),
                },
                dest=task_id,
            ),
            root=root,
        )
        mark_stall_recovery_queued(task_id, root=root)
        record_running_error(task_id, "uncommitted_delivery", root=root)


def invalidate_task_merge(task_id: str, *, root: Path) -> None:
    """Remove a stale delivery from scheduling while retaining its action history."""

    repo = resolve_root(root)
    with process_lock:
        pending = _read(repo)
        if task_id in pending:
            _write(repo, [entry for entry in pending if entry != task_id])


def pending_task_merges(root: Path) -> set[str]:
    repo = resolve_root(root)
    with process_lock:
        return set(_read(repo))


def retry_pending_task_merges(root: Path, *, feature_id: str | None = None) -> list[str]:
    """Retry durable task merges and return ids completed on this pass."""

    repo = resolve_root(root)
    from cascade.task.action_recovery import recovery_actions, reconcile_completed_task_delivery
    for historical in recovery_actions(root=repo):
        if historical.get("action_kind") != _QUEUED_MERGE_KIND or historical.get("recovery_state") == "completed":
            continue
        task_id = (historical.get("metadata") or {}).get("task_id")
        if feature_id is not None and not _owned_by_feature(task_id, feature_id, repo):
            continue
        if task_id and _already_completed_equivalent(task_id, repo):
            reconcile_completed_task_delivery(task_id, root=repo)
            _clear_delivery_blockers(task_id, repo)
    completed: list[str] = []
    removable: list[str] = []
    with process_lock:
        pending = _read(repo)
    for task_id in pending:
        if feature_id is not None and not _owned_by_feature(task_id, feature_id, repo):
            continue
        # A live parent/source turn is a scheduling wait, not a failed repair.
        # Keep the queue and finite action-attempt budget intact until idle.
        if _delivery_turn_busy(task_id, repo):
            continue
        from cascade.task.worktree import task_worktree_has_changes
        if task_worktree_has_changes(task_id, root=repo):
            defer_uncommitted_delivery(task_id, root=repo)
            continue
        action = _queued_merge_action(task_id, repo)
        evidence = queued_delivery_evidence(task_id, root=repo)
        if (
            evidence is not None
            and _merge_head_pair(task_id, repo) is not None
            and not delivery_evidence_is_current(task_id, evidence, root=repo)
        ):
            # A branch moved after validation. Synchronize through the normal
            # guarded branch service, then return the original Task to the
            # supervised final gate. The old action and validation stay in the
            # ledger as history, but cannot authorize this new head pair.
            if _request_delivery_revalidation(task_id, evidence, repo):
                removable.append(task_id)
            continue
        if _already_completed_equivalent(task_id, repo):
            from cascade.task.action_recovery import reconcile_completed_task_delivery
            reconcile_completed_task_delivery(task_id, root=repo)
            _clear_delivery_blockers(task_id, repo)
            completed.append(task_id)
            removable.append(task_id)
            continue
        state = action.get("recovery_state")
        # A supervisor can be interrupted after recording success but before it
        # prunes the legacy queue.  Removing that entry must not replay merge
        # or rollup.
        if state == "completed":
            removable.append(task_id)
            continue
        if state in {"awaiting_owner_decision", "awaiting_human_gate", "blocked", "running"}:
            if state == "blocked":
                removable.append(task_id)
            continue

        if _unchanged_parent_lifecycle_mismatch(task_id, action, repo):
            # The completed parent cannot become mergeable by replaying the
            # child merge.  Its exact Feature repair generation owns progress.
            continue

        action = resume_action(
            _queued_merge_action_id(task_id),
            root=repo,
            execute=lambda _context, task_id=task_id: _resume_queued_merge(task_id, repo),
        )
        if action.get("recovery_state") == "completed":
            completed.append(task_id)
            removable.append(task_id)
        elif action.get("recovery_state") == "blocked":
            removable.append(task_id)
    if removable:
        with process_lock:
            latest = _read(repo)
            removed = set(removable)
            _write(repo, [task_id for task_id in latest if task_id not in removed])
    return completed


def _request_delivery_revalidation(
    task_id: str, evidence: dict[str, str], root: Path
) -> bool:
    """Synchronize a stale delivery and queue one exact-pair validation turn."""

    from cascade.task.execution import mark_stall_recovery_queued
    from cascade.task.wiring import invalidate_validated_delivery
    from cascade.watchdog.events import read_events
    from cascade.workspace.branch_synchronization import update_integration_branch

    synchronization = update_integration_branch(task_id, root=root)
    if not synchronization.ok:
        return False
    heads = _merge_head_pair(task_id, root)
    if heads is None:
        return False
    replacement = {
        "task_id": task_id,
        "deliverable_sha": heads[0],
        "feature_base_sha": heads[1],
    }
    invalidate_validated_delivery(task_id, root=root)
    events, _ = read_events(task_id, 0, root=root)
    if not any(
        event.type == "TaskValidationRetryRequested"
        and event.payload.get("reason") == "delivery_heads_moved"
        and event.payload.get("replacement_pair") == replacement
        for event in events
    ):
        append_event(
            task_id,
            Event(
                type="TaskValidationRetryRequested",
                ts=datetime.now(timezone.utc),
                payload={
                    "task_id": task_id,
                    "reason": "delivery_heads_moved",
                    "stale_validation": dict(evidence),
                    "replacement_pair": replacement,
                    "instruction": (
                        "The Task source or Feature target moved after final validation. "
                        "Use the existing checkout and implementation, run the scoped "
                        "Cascade swe_run_tests command on the clean committed tree, and "
                        "publish replacement evidence only after it is green."
                    ),
                },
                dest=task_id,
            ),
            root=root,
        )
    mark_stall_recovery_queued(task_id, root=root)
    return True


def _owned_by_feature(task_id: str, feature_id: str, root: Path) -> bool:
    try:
        return read_doc(task_id, root=root).meta.parent == feature_id
    except NotFound:
        return False


def _delivery_turn_busy(task_id: str, root: Path) -> bool:
    from cascade.workspace.kickoff import _graph_has_inflight_turn
    try:
        task = read_doc(task_id, root=root)
    except NotFound:
        return False
    parent = task.meta.parent
    return bool(parent) and (
        _graph_has_inflight_turn(parent, "feature", root=root, feature_id=None)
        or _graph_has_inflight_turn(task_id, "task", root=root, feature_id=parent)
    )


def _resume_queued_merge(task_id: str, root: Path) -> ActionResult:
    """Execute the existing merge boundary once and classify its result."""

    from cascade.boss.merge import merge_task_branch

    result = merge_task_branch(task_id, root=root)
    metadata = _merge_outcome_metadata(task_id, result, root)
    if result.ok or _already_completed_equivalent(task_id, root):
        _clear_delivery_blockers(task_id, root)
        if result.ok:
            from cascade.boss.rollup import on_task_merged

            try:
                on_task_merged(task_id, root=root)
            except Exception:
                # The merge is durable; closeout scanning can recover an
                # independent rollup failure without replaying the merge.
                pass
        metadata["already_completed"] = not result.ok
        return ActionResult(metadata=metadata)

    reason = result.reason or "merge_refused"
    if reason == "source_dirty":
        # A writer can arrive after the queue's preflight. Preserve the later
        # edits and return to the original Task instead of terminally blocking.
        defer_uncommitted_delivery(task_id, root=root)
        return ActionResult("failed", "transient_retry", metadata)
    if reason == "branch_conflict":
        _record_merge_refusal(task_id, result, root)
        handoff_semantic_conflict(
            _queued_merge_action_id(task_id),
            root=root,
            scope="task_code",
            evidence=metadata,
        )
        return ActionResult("failed", "owner_decision", metadata)
    if reason in {
        "busy", "not_active", "checkout_missing", "merge_target_missing", "wrong_branch", "post_merge_failed",
    }:
        if reason != "busy":
            _record_merge_refusal(task_id, result, root)
        if reason == "not_active" and _parent_is_completed(task_id, root):
            mismatch = _store_parent_lifecycle_mismatch(task_id, root)
            metadata["parent_lifecycle_mismatch"] = mismatch
            classification = "parent_lifecycle_mismatch"
        else:
            classification = (
                "transient_retry"
                if reason in {"busy", "not_active"}
                else "deterministic_repair"
            )
        return ActionResult("failed", classification, metadata)
    if reason not in {"task_not_found", "wrong_column", "not_mergeable"}:
        _record_merge_refusal(task_id, result, root)
    return ActionResult("failed", "terminal_blocker", metadata)


def _parent_is_completed(task_id: str, root: Path) -> bool:
    """Distinguish a lifecycle mismatch from an active-parent refusal."""

    try:
        task = read_doc(task_id, root=root)
        return bool(
            task.meta.parent
            and read_doc(task.meta.parent, root=root).meta.status == "completed"
        )
    except NotFound:
        return False


def _unchanged_parent_lifecycle_mismatch(
    task_id: str, action: Mapping[str, Any], root: Path
) -> bool:
    """Observe an unchanged mismatch without spending another merge attempt."""

    if action.get("failure_classification") != "parent_lifecycle_mismatch":
        return False
    metadata = action.get("metadata")
    recorded = (
        metadata.get("parent_lifecycle_mismatch")
        if isinstance(metadata, Mapping)
        else None
    )
    if not isinstance(recorded, Mapping):
        return False
    current = _parent_lifecycle_mismatch(task_id, root)
    if current is None:
        return False
    return recorded.get("authoritative_generation") == current.get(
        "authoritative_generation"
    )


def _store_parent_lifecycle_mismatch(task_id: str, root: Path) -> dict[str, Any]:
    """Attach the exact completed-parent generation to the original action."""

    mismatch = _parent_lifecycle_mismatch(task_id, root)
    if mismatch is None:
        raise ActionRecoveryError("completed parent lifecycle evidence disappeared")
    action_id = _queued_merge_action_id(task_id)
    action = load_action(action_id, root=root)
    if action is None:
        raise ActionRecoveryError("queued delivery action disappeared")
    metadata = dict(action.get("metadata") or {})
    metadata["parent_lifecycle_mismatch"] = mismatch
    replace_action_metadata(action_id, metadata, root=root)
    return mismatch


def _parent_lifecycle_mismatch(
    task_id: str, root: Path
) -> ParentLifecycleMismatch | None:
    """Build the canonical evidence generation for a completed Feature parent.

    Every value here belongs to an existing authority: board documents,
    registered mutation ownership, queued/repair actions, review state,
    comments, dependencies, validation heads, or the Task execution lease.
    Unknown legacy values remain ``None`` and therefore fail closed without
    manufacturing an approval or owner.
    """

    try:
        task = read_doc(task_id, root=root)
        feature_id = task.meta.parent
        if not feature_id:
            return None
        feature = read_doc(feature_id, root=root)
    except NotFound:
        return None
    if feature.meta.tier != "feature" or feature.meta.status != "completed":
        return None

    try:
        from cascade.workspace.integration_worktree import resolve_mutation_owner

        owner_root: str | None = resolve_mutation_owner(
            feature_id, trunk=root
        ).resolve().as_posix()
    except Exception:
        owner_root = None

    from cascade.feature.repair import current_feature_repair_record
    from cascade.review import review_record_for_feature
    from cascade.task.execution import execution_view

    repair = current_feature_repair_record(feature_id, root=root)
    review = review_record_for_feature(feature_id, root=root)
    execution = execution_view(task_id, root=root) or {}
    validation = queued_delivery_evidence(task_id, root=root)
    heads = _merge_head_pair(task_id, root)

    try:
        from cascade.comments.store import read_comments

        comments = [
            {
                "id": row.id,
                "state": row.state,
                "blocking": row.blocking,
                "parent": row.parent,
            }
            for row in read_comments(feature_id, root=root, readonly=True)
            if row.parent is None
        ]
    except Exception:
        comments = None

    board_dependencies: list[dict[str, Any]] = []
    for dependency in feature.meta.depends_on:
        try:
            dependency_status: str | None = read_doc(
                dependency, root=root
            ).meta.status
        except NotFound:
            dependency_status = None
        board_dependencies.append(
            {"work_id": dependency, "status": dependency_status}
        )

    evidence: dict[str, Any] = {
        "owner": {
            "tier": "feature",
            "work_id": feature_id,
            "mutation_root": owner_root,
        },
        "parent": {
            "feature_id": feature_id,
            "feature_status": feature.meta.status,
            "epic_id": feature.meta.parent,
        },
        "delivery_action": {
            "action_id": _queued_merge_action_id(task_id),
            "action_kind": _QUEUED_MERGE_KIND,
        },
        "repair_action": (
            {
                key: repair.get(key)
                for key in (
                    "action_id",
                    "generation",
                    "request_id",
                    "task_id",
                    "phase",
                    "blocker",
                    "next_action",
                )
            }
            if isinstance(repair, Mapping)
            else None
        ),
        "tested_heads": {
            "validation": validation,
            "current_source": heads[0] if heads else None,
            "current_target": heads[1] if heads else None,
        },
        "review_obligation": (
            {
                key: review.get(key)
                for key in (
                    "current_generation",
                    "generation",
                    "action_id",
                    "publication_action_id",
                    "url",
                    "state",
                    "closed",
                    "source_branch",
                    "target_branch",
                    "source_head",
                    "target_head",
                    "accepted_source_head",
                    "accepted_target_head",
                    "accepted_merge_sha",
                    "reconciliation_status",
                )
            }
            if isinstance(review, Mapping)
            else None
        ),
        "gates": {
            "approved_at": (
                feature.meta.approved_at.isoformat()
                if feature.meta.approved_at
                else None
            ),
            "plan_approved_at": (
                feature.meta.plan_approved_at.isoformat()
                if feature.meta.plan_approved_at
                else None
            ),
            "comments": comments,
            "dependencies": board_dependencies,
        },
        "execution_lease": {
            key: execution.get(key)
            for key in (
                "phase",
                "health",
                "attempt",
                "owner_pid",
                "owner_start_token",
                "heartbeat_at",
            )
        },
    }
    from cascade.watchdog.incidents import authoritative_generation

    generation = authoritative_generation(
        work_id=task_id,
        tier="task",
        evidence=evidence,
        capability="feature_repair",
    )
    return {
        "schema_version": 1,
        "failure_class": "parent_lifecycle_mismatch",
        "authoritative_generation": generation,
        "accountable_owner": f"feature_team:{feature_id}",
        "selected_operation": "feature_repair",
        "evidence": evidence,
    }



def handoff_semantic_conflict(
    action_id: str,
    *,
    root: Path,
    scope: str | None,
    evidence: dict | None,
) -> dict:
    """Record a scope-classified semantic handoff for an existing action.

    The caller must classify scope explicitly. Conflict paths are evidence, not
    authority to promote a task/code conflict to Epic Team.
    """

    owner = _SEMANTIC_CONFLICT_OWNERS.get(scope or "")
    if owner is None:
        raise ActionRecoveryError("semantic conflict scope is missing or ambiguous")
    if not isinstance(evidence, dict):
        raise ActionRecoveryError("semantic conflict evidence must be a mapping")
    required = ("source_sha", "target_sha", "reason", "conflict_paths")
    if any(key not in evidence for key in required):
        raise ActionRecoveryError("semantic conflict evidence is incomplete")
    if evidence["reason"] != "branch_conflict":
        raise ActionRecoveryError("semantic handoff requires a branch conflict")
    if not isinstance(evidence["conflict_paths"], list):
        raise ActionRecoveryError("semantic conflict paths must be a list")

    identity_evidence = {
        "source_sha": evidence["source_sha"],
        "target_sha": evidence["target_sha"],
        "reason": evidence["reason"],
        "conflict_paths": sorted(str(path) for path in evidence["conflict_paths"]),
    }
    encoded = json.dumps(
        {"action_id": action_id, "scope": scope, "evidence": identity_evidence},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    decision_id = f"semantic-conflict:{sha256(encoded).hexdigest()}"
    from cascade.task.action_recovery import capture_and_route_action_failure
    action = load_action(action_id, root=root) or {}
    task_id = (action.get("metadata") or {}).get("task_id")
    if task_id:
        task = read_doc(task_id, root=root)
        recipient = task_id if scope == "task_code" else read_doc(task.meta.parent, root=root).meta.parent
        capture_and_route_action_failure(
            action_id, _QUEUED_MERGE_KIND, affected_work_id=task_id,
            intended_target_ref=f"feat/{task.meta.parent}", root=root,
            failure_code="branch_conflict", safe_summary="Resolve the owned Task branch conflict, commit scoped edits and run supervised validation.",
            evidence={**identity_evidence, "supervisor": task.meta.parent},
            conflicting_paths=evidence["conflict_paths"],
            owning_team={"kind": owner, "work_id": recipient},
            review_id=decision_id,
        )
    return record_owner_decision(
        action_id,
        decision_id,
        root=root,
        owner=owner,
        metadata={"scope": scope, "evidence": identity_evidence},
    )


def handoff_queued_merge_semantic_conflict(
    task_id: str,
    *,
    root: Path,
    scope: str | None,
    evidence: dict | None,
) -> dict:
    """Supervisor convenience wrapper for the stable queued-merge action."""

    return handoff_semantic_conflict(
        _queued_merge_action_id(task_id), root=root, scope=scope, evidence=evidence
    )


def resolve_semantic_conflict(
    action_id: str,
    decision_id: str,
    resolution_id: str,
    *,
    root: Path,
    metadata: dict | None = None,
) -> dict:
    """Authorize retry of exactly the action and decision named by a resolution."""

    return record_owner_resolution(
        action_id, decision_id, resolution_id, root=root, metadata=metadata
    )


def _merge_outcome_metadata(task_id: str, result, root: Path) -> dict:
    heads = _merge_head_pair(task_id, root)
    source_sha, target_sha = heads if heads is not None else (None, None)
    return {
        "task_id": task_id,
        "reason": result.reason,
        "branch": result.branch,
        "target_branch": result.target_branch,
        "merge_sha": result.merge_sha,
        "conflict_paths": list(result.conflict_paths),
        "source_sha": source_sha,
        "target_sha": target_sha,
    }


def _already_completed_equivalent(task_id: str, root: Path) -> bool:
    """Recognize a merge committed by an interrupted earlier supervisor."""

    try:
        return read_doc(task_id, root=root).meta.status == "completed"
    except NotFound:
        return False


def _merge_head_pair(task_id: str, root: Path) -> tuple[str, str] | None:
    """The source and target refs that determine a task merge conflict."""

    try:
        task = read_doc(task_id, root=root)
    except NotFound:
        return None
    if task.meta.status != "active" or not task.meta.parent:
        return None
    refs = (f"refs/heads/task/{task_id}", f"refs/heads/feat/{task.meta.parent}")
    heads: list[str] = []
    for ref in refs:
        result = _run(["rev-parse", "--verify", ref], root, check=False)
        if result.returncode != 0:
            return None
        heads.append(result.stdout.strip())
    return heads[0], heads[1]


def _record_merge_refusal(task_id: str, result, root: Path) -> None:
    heads = _merge_head_pair(task_id, root)
    source_sha, target_sha = heads if heads is not None else (None, None)
    reason = result.reason or "merge_refused"
    paths = tuple(result.conflict_paths)
    if not mark_merge_blocked(
        task_id,
        root=root,
        reason=reason,
        conflict_paths=paths,
        source_sha=source_sha,
        target_sha=target_sha,
    ):
        return
    detail = f" Conflicting files: {', '.join(paths)}." if paths else ""
    recovery = (
        "Resolve the Task branch against its Feature branch, then retry Merge task."
        if reason == "branch_conflict"
        else "Check the merge refusal, then retry Merge task."
    )
    message = f"Task {task_id} could not merge ({reason}).{detail} {recovery}"
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "task_merge_blocked",
                "id": task_id,
                "reason": reason,
                "conflict_paths": list(paths),
                "message": message,
            },
            dest="war_room",
        ),
        root=root,
    )


def _clear_delivery_blockers(task_id: str, root: Path) -> None:
    from cascade.watchdog.blockage import reconcile_direct_report_blockage
    child = read_doc(task_id, root=root)
    if not child.meta.parent:
        return
    matching_incidents = _matching_delivery_blocker_ids(task_id, root)
    if not matching_incidents:
        return
    parent = read_doc(child.meta.parent, root=root)
    for blocker in list(parent.meta.monitoring_blockers):
        if blocker.child_id != task_id:
            continue
        if blocker.incident_id not in matching_incidents:
            continue
        # Wake planning before removing the cause. A crash may replay this
        # notification, but must never leave an unblocked Feature silently
        # publishing an incomplete task decomposition.
        from cascade.watchdog.events import read_events

        event_type = "TaskDeliveryBlockageCleared"
        events, _ = read_events(parent.meta.id, 0, root=root)
        if not any(e.type == event_type and e.payload.get("incident_id") == blocker.incident_id
                   for e in events):
            append_event(parent.meta.id, Event(
                type=event_type, ts=datetime.now(timezone.utc), dest=parent.meta.id,
                payload={"task_id": task_id, "incident_id": blocker.incident_id,
                         "body": "Completed Task delivery has cleared its supervisor blocker. Resume planning, mint any remaining planned Tasks, and confirm the full scope before closeout."},
            ), root=root)
        reconcile_direct_report_blockage(parent, child, root=root, incident_id=blocker.incident_id)
        parent = read_doc(child.meta.parent, root=root)


def _matching_delivery_blocker_ids(task_id: str, root: Path) -> set[str]:
    """Return derived incidents belonging to this Task's original merge action."""

    action = load_action(_queued_merge_action_id(task_id), root=root)
    if action is None or (action.get("metadata") or {}).get("task_id") != task_id:
        return set()
    from cascade.task.supervisor_recovery import delivery_incident_ids

    incidents = delivery_incident_ids(task_id, root=root)
    from cascade.task.execution import execution_view

    attempt = (execution_view(task_id, root=root) or {}).get("attempt")
    if isinstance(attempt, int):
        incidents.add(f"{task_id}:delivery:{attempt}")
    recovery = action.get("recovery")
    marker = recovery.get("routing_marker") if isinstance(recovery, dict) else None
    if isinstance(marker, dict):
        review_id = marker.get("review_id")
        if isinstance(review_id, str) and review_id:
            incidents.add(f"{task_id}:delivery:{review_id}")
    return incidents
