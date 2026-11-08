"""Epic Team recovery for accepted stacked reviews stranded off the Epic line."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess

from cascade.board.errors import GitError
from cascade.epic.registry import register_epic_tool
from cascade.review import (
    _ensure_opened_toast,
    find_merge_request,
    persist_stacked_reconciliation_review,
)
from cascade.task.action_recovery import (
    ActionNotFound,
    load_action,
    record_owner_resolution,
    replace_action_metadata,
)
from cascade.tracking import MergeRequest, create_merge_request
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    locate_trunk,
    merged_board,
)


_ACTION_KIND = "stacked_review_integration_gap"


def resume_owner(
    request_id: str,
    *,
    epic_id: str,
    root: Path,
    expected_generation: str | None = None,
) -> dict[str, object]:
    """Wake an absent Epic planning owner through its durable graph queue."""

    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("a stable recovery request_id is required")
    trunk = locate_trunk(root)
    from datetime import datetime, timezone
    from cascade.watchdog.events import append_event, read_events
    from cascade.watchdog.types import Event
    from cascade.workspace.kickoff import (
        graph_turn_owner_is_live,
        kickoff_graph_queue_event,
    )

    events, _ = read_events(epic_id, 0, root=trunk)
    existing = next(
        (
            event
            for event in events
            if event.type == "EpicRecoveryRequested"
            and event.payload.get("request_id") == request_id
            and event.payload.get("epic_id") == epic_id
        ),
        None,
    )
    if existing is not None:
        scheduled = kickoff_graph_queue_event(epic_id, root=trunk)
        return {
            "ok": True,
            "epic_id": epic_id,
            "request_id": request_id,
            "outcome": "pending_owner_result",
            "acknowledged": scheduled,
            "durable_result": False,
        }

    _admit_epic_action(
        epic_id,
        "resume_planning_owner",
        root=trunk,
        expected_generation=expected_generation,
    )
    if graph_turn_owner_is_live(epic_id):
        return {
            "ok": True,
            "epic_id": epic_id,
            "request_id": request_id,
            "outcome": "already_running",
            "durable_result": False,
        }
    with process_lock:
        events, _ = read_events(epic_id, 0, root=trunk)
        existing = next(
            (
                event
                for event in events
                if event.type == "EpicRecoveryRequested"
                and event.payload.get("request_id") == request_id
            ),
            None,
        )
        if existing is None:
            append_event(
                epic_id,
                Event(
                    type="EpicRecoveryRequested",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "epic_id": epic_id,
                        "request_id": request_id,
                        "action": "resume_planning_owner",
                    },
                    dest=epic_id,
                ),
                root=trunk,
            )
    scheduled = kickoff_graph_queue_event(epic_id, root=trunk)
    return {
        "ok": True,
        "epic_id": epic_id,
        "request_id": request_id,
        "outcome": "pending_owner_result",
        "acknowledged": scheduled,
        "durable_result": False,
    }


def restore_feature_dispatch(
    feature_id: str,
    *,
    epic_id: str,
    root: Path,
    expected_generation: str | None = None,
) -> dict[str, object]:
    """Dispatch one proven direct Feature through canonical dispatch law."""

    trunk = locate_trunk(root)
    _admit_epic_action(
        epic_id,
        f"restore_child_dispatch:{feature_id}",
        root=trunk,
        expected_generation=expected_generation,
    )
    from cascade.watchdog.dispatch import dispatch_feature
    from cascade.war_room.serialize import dispatch_result_to_dict
    from cascade.workspace.kickoff import deferred_kickoffs

    # dispatch_feature repeats the parent and every approval/comment/dependency
    # check under the dispatch lock. Model work begins only after that lock.
    with deferred_kickoffs():
        result = dispatch_feature(
            feature_id, "boss", root=trunk, expected_parent=epic_id
        )
    return {
        **dispatch_result_to_dict(result),
        "epic_id": epic_id,
        "feature_id": feature_id,
        "outcome": "pending_feature_result" if result.ok else "refused",
        "durable_result": False,
    }


def recover_feature(feature_id: str, *, epic_id: str, root: Path) -> dict[str, object]:
    """Ask one active direct Feature to reconcile its owned durable actions."""

    trunk = locate_trunk(root)
    board = merged_board(trunk)
    epic = board.by_id.get(epic_id)
    feature = board.by_id.get(feature_id)
    if epic is None or epic.tier != "epic" or epic.status != "active":
        raise PermissionError("Epic recovery owner is not active")
    if feature is None or feature.tier != "feature" or feature.parent != epic_id:
        raise PermissionError("recovery is scoped to a direct Feature")
    from cascade.team_supervision import supervise_child

    result = supervise_child(feature_id, "recover", root=trunk, epic_id=epic_id)
    return {
        **result,
        "epic_id": epic_id,
        "feature_id": feature_id,
        "outcome": result.get("outcome", "pending_feature_result"),
        "durable_result": False,
    }


def reconcile_completion_rollup(
    *,
    epic_id: str,
    root: Path,
    expected_generation: str | None = None,
) -> dict[str, object]:
    """Reconcile one Epic closeout and report its durable terminal state."""

    return _reconcile_epic_completion(
        epic_id,
        action="reconcile_completion_rollup",
        root=root,
        expected_generation=expected_generation,
    )


def publish_integration_review(
    epic_id: str,
    *,
    root: Path,
    expected_generation: str | None = None,
) -> dict[str, object]:
    """Publish completed Epic work through its existing closeout path."""

    return _reconcile_epic_completion(
        epic_id,
        action="publish_integration_review",
        root=root,
        expected_generation=expected_generation,
    )


def _reconcile_epic_completion(
    epic_id: str,
    *,
    action: str,
    root: Path,
    expected_generation: str | None,
) -> dict[str, object]:
    trunk = locate_trunk(root)
    from cascade.boss.epic_complete import (
        epic_completed_recorded,
        try_complete_epic_result,
    )

    if epic_completed_recorded(epic_id, root=trunk):
        return {
            "ok": True,
            "epic_id": epic_id,
            "generation": expected_generation,
            "outcome": "completed",
            "durable_result": True,
            "reason": None,
            "review_url": None,
            "close_stage": "completed",
            "forge_state": "unknown",
            "blocker_ids": [],
            "conflict_paths": [],
        }
    observation = _admit_epic_action(
        epic_id,
        action,
        root=trunk,
        expected_generation=expected_generation,
    )
    _require_clean_epic_worktree(epic_id, root=trunk)
    result = try_complete_epic_result(epic_id, root=trunk)
    terminal = epic_completed_recorded(epic_id, root=trunk)
    return {
        "ok": result.ok,
        "epic_id": epic_id,
        "generation": str(observation.generation),
        "outcome": "completed" if terminal else "pending_or_retryable",
        "durable_result": terminal,
        "reason": result.reason,
        "review_url": result.review_url,
        "close_stage": result.close_stage,
        "forge_state": result.forge_state,
        "blocker_ids": list(result.blocker_ids),
        "conflict_paths": list(result.conflict_paths),
    }


def _admit_epic_action(
    epic_id: str,
    action: str,
    *,
    root: Path,
    expected_generation: str | None,
):
    """Reread canonical gates and bind an effect to one Epic generation."""

    from cascade.watchdog.audit import project_audit_observation

    observation = project_audit_observation(epic_id, root=root)
    if observation.tier != "epic":
        raise PermissionError("recovery owner is not an Epic")
    if expected_generation is not None and str(observation.generation) != str(
        expected_generation
    ):
        raise RuntimeError("Epic recovery generation changed")
    evidence = observation.evidence
    if evidence.errors:
        raise RuntimeError(f"Epic recovery evidence unavailable: {evidence.errors[0]}")
    parent_action = evidence.parent_action
    if (
        parent_action is None
        or parent_action.responsible_work_id != epic_id
        or parent_action.candidate_action != action
        or parent_action.state == "gated"
    ):
        raise PermissionError("Epic recovery action is no longer admitted")
    return observation


def _require_clean_epic_worktree(epic_id: str, *, root: Path) -> None:
    entry = get_integration_worktree(root, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=entry.path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if status.returncode != 0:
        raise GitError(status.stderr.strip() or "cannot inspect epic worktree")
    dirty = [
        line
        for line in status.stdout.splitlines()
        if len(line) < 4 or not line[3:].split(" -> ")[-1].startswith(".cascade/")
    ]
    if dirty:
        raise PermissionError("dirty Epic worktree requires its owner")


def reconcile_stacked_review_gap(
    action_id: str, *, epic_id: str, root: Path
) -> dict[str, object]:
    """Create or reuse the Epic-targeted review requested by one gap action.

    The recovery action is the stable idempotency record.  The Epic Team may
    retry this tool freely: the same source/target review is found before a
    creation is attempted, and the action keeps the review identity and the
    accepted predecessor review that originated it.
    """

    trunk = locate_trunk(root)
    # The forge lookup/create and registry replacement must be one Cascade
    # critical section.  This prevents two duplicate callbacks from both
    # deciding that no follow-up exists.
    with process_lock:
        action = load_action(action_id, root=trunk)
        if action is None:
            raise ActionNotFound(action_id)
        evidence, decision_id = _gap_evidence(action, epic_id=epic_id)
        existing = _reconciliation_from_metadata(action, evidence)
        if existing is None:
            mr = _find_or_create_review(evidence, root=trunk)
            action = _record_reconciliation(action, evidence, mr, root=trunk)
        else:
            mr = existing

        record = persist_stacked_reconciliation_review(
            str(evidence["feature_id"]),
            mr,
            action_id=action_id,
            originating_review=dict(evidence["accepted_review"]),
            root=trunk,
        )
        _ensure_opened_toast(str(evidence["feature_id"]), mr, record, root=trunk)
        resolved = _resolve_gap_decision(
            action, decision_id, evidence, mr, root=trunk
        )
    return {
        "action_id": action_id,
        "feature_id": evidence["feature_id"],
        "epic_id": epic_id,
        "review_url": mr.url,
        "target_branch": mr.target_branch,
        "originating_review": dict(evidence["accepted_review"]),
        "recovery_state": resolved["recovery_state"],
    }


def _gap_evidence(action: dict[str, object], *, epic_id: str) -> tuple[dict[str, object], str]:
    if action.get("action_kind") != _ACTION_KIND:
        raise ValueError(f"{action.get('action_id')} is not a stacked review recovery action")
    stored = action.get("metadata")
    if not isinstance(stored, dict):
        raise ValueError("stacked review recovery is missing evidence")
    evidence = {
        key: stored[key]
        for key in (
            "feature_id",
            "epic_id",
            "predecessor_id",
            "expected_target_branch",
            "accepted_review",
        )
        if key in stored
    }
    if evidence.get("epic_id") != epic_id:
        raise ValueError(f"recovery action does not belong to {epic_id}")
    expected = f"epic/{epic_id}"
    if evidence.get("expected_target_branch") != expected:
        raise ValueError("stacked review recovery has an invalid Epic target")
    accepted = evidence.get("accepted_review")
    if not isinstance(accepted, dict):
        raise ValueError("stacked review recovery is missing accepted-review provenance")
    source = accepted.get("source_branch")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("accepted-review provenance is missing its source branch")
    decisions = action.get("owner_decisions")
    if not isinstance(decisions, list):
        raise ValueError("stacked review recovery is missing its Epic Team decision")
    decision = next(
        (
            row for row in decisions
            if isinstance(row, dict)
            and row.get("owner") == "epic_team"
            and row.get("metadata") == evidence
        ),
        None,
    )
    if not isinstance(decision, dict) or not isinstance(decision.get("decision_id"), str):
        raise ValueError("stacked review recovery is missing its Epic Team decision")
    return dict(evidence), decision["decision_id"]


def _find_or_create_review(evidence: dict[str, object], *, root: Path) -> MergeRequest:
    epic_id = str(evidence["epic_id"])
    entry = get_integration_worktree(root, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    source = str(dict(evidence["accepted_review"])["source_branch"])
    target = str(evidence["expected_target_branch"])
    existing = find_merge_request(entry.path, source_branch=source, target_branch=target)
    if existing is not None:
        return existing
    feature_id = str(evidence["feature_id"])
    original_url = str(dict(evidence["accepted_review"]).get("url") or "unknown review")
    return create_merge_request(
        entry.path,
        title=f"{feature_id}: reconcile accepted stacked review",
        body=(
            f"Reconciles accepted stacked review {original_url} into `{target}`. "
            "This follow-up is managed by the Epic Team."
        ),
        source_branch=source,
        target_branch=target,
        draft=False,
    )


def _reconciliation_from_metadata(
    action: dict[str, object], evidence: dict[str, object]
) -> MergeRequest | None:
    metadata = action.get("metadata")
    if not isinstance(metadata, dict):
        return None
    row = metadata.get("reconciliation_review")
    if not isinstance(row, dict):
        return None
    try:
        mr = MergeRequest(
            url=str(row["url"]),
            number=str(row["number"]) if row.get("number") is not None else None,
            forge=str(row["forge"]),  # type: ignore[arg-type]
            source_branch=str(row["source_branch"]),
            target_branch=str(row["target_branch"]),
            draft=bool(row.get("draft", False)),
        )
    except KeyError:
        return None
    if (
        mr.source_branch != dict(evidence["accepted_review"])["source_branch"]
        or mr.target_branch != evidence["expected_target_branch"]
    ):
        raise ValueError("stacked review recovery has conflicting reconciliation evidence")
    return mr


def _record_reconciliation(
    action: dict[str, object], evidence: dict[str, object], mr: MergeRequest, *, root: Path
) -> dict[str, object]:
    metadata = dict(evidence)
    metadata["reconciliation_review"] = {
        "url": mr.url,
        "number": mr.number,
        "forge": mr.forge,
        "source_branch": mr.source_branch,
        "target_branch": mr.target_branch,
        "draft": mr.draft,
    }
    return replace_action_metadata(str(action["action_id"]), metadata, root=root)


def _resolve_gap_decision(
    action: dict[str, object],
    decision_id: str,
    evidence: dict[str, object],
    mr: MergeRequest,
    *,
    root: Path,
) -> dict[str, object]:
    identity = json.dumps(
        {"action_id": action["action_id"], "target_branch": evidence["expected_target_branch"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    resolution_id = f"stacked-review-reconciliation:{sha256(identity).hexdigest()}"
    metadata = {"review_url": mr.url, "target_branch": mr.target_branch}
    return record_owner_resolution(
        str(action["action_id"]), decision_id, resolution_id, root=root, metadata=metadata
    )


register_epic_tool("reconcile_stacked_review_gap", reconcile_stacked_review_gap)
register_epic_tool("resume_owner", resume_owner)
register_epic_tool("restore_feature_dispatch", restore_feature_dispatch)
register_epic_tool("recover_feature", recover_feature)
register_epic_tool("publish_integration_review", publish_integration_review)
register_epic_tool("reconcile_completion_rollup", reconcile_completion_rollup)
