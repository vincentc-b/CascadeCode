"""Durable retry queue for automatic task-to-feature merges."""

from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.gitutil import _run
from cascade.board.store import read_doc
from cascade.task.action_recovery import (
    ActionRecoveryError,
    ActionResult,
    create_or_load_action,
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
    "task_code": "feature_team",
    "cross_feature": "epic_team",
    "epic_contract": "epic_team",
}


def _path(root: Path) -> Path:
    return root / ".cascade" / "pending-task-merges.json"


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
    return action


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
    with process_lock:
        pending = _read(repo)
        if task_id not in pending:
            pending.append(task_id)
            _write(repo, pending)


def pending_task_merges(root: Path) -> set[str]:
    repo = resolve_root(root)
    with process_lock:
        return set(_read(repo))


def retry_pending_task_merges(root: Path) -> list[str]:
    """Retry durable task merges and return ids completed on this pass."""

    repo = resolve_root(root)
    completed: list[str] = []
    removable: list[str] = []
    with process_lock:
        pending = _read(repo)
    for task_id in pending:
        action = _queued_merge_action(task_id, repo)
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


def _resume_queued_merge(task_id: str, root: Path) -> ActionResult:
    """Execute the existing merge boundary once and classify its result."""

    from cascade.boss.merge import merge_task_branch

    result = merge_task_branch(task_id, root=root)
    metadata = _merge_outcome_metadata(task_id, result, root)
    if result.ok or _already_completed_equivalent(task_id, root):
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
        "busy", "checkout_missing", "merge_target_missing", "wrong_branch", "post_merge_failed",
    }:
        if reason != "busy":
            _record_merge_refusal(task_id, result, root)
        classification = "transient_retry" if reason == "busy" else "deterministic_repair"
        return ActionResult("failed", classification, metadata)
    if reason not in {"task_not_found", "wrong_column", "not_mergeable"}:
        _record_merge_refusal(task_id, result, root)
    return ActionResult("failed", "terminal_blocker", metadata)



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
