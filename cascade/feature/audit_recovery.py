"""Concrete Feature-team adapters for proven parent audit incidents.

The health auditor owns admission and receipts.  This module owns the last,
Feature-scoped safety check and delegates every mutation to the normal graph,
dispatch, action-recovery, review, and completion paths.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cascade.feature.registry import register_feature_tool
from cascade.task.action_recovery import load_action
from cascade.watchdog.audit import AuditObservation, project_audit_observation
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    locate_trunk,
)

_HARD_GATE_PREFIXES = (
    "approval",
    "comment",
    "dependency",
    "human_gate",
    "not_approved",
    "review_threads_blocking",
)


def resume_planning_owner(
    feature_id: str, *, generation: str, root: Path
) -> dict[str, object]:
    """Wake an interrupted Feature graph without manufacturing new input."""

    admitted = _admit_parent_action(
        feature_id, "resume_planning_owner", generation=generation, root=root
    )
    if isinstance(admitted, dict):
        return admitted
    observation, product, _worktree = admitted

    # Only an existing durable continuation is legal here.  A Feature with no
    # checkpoint input needs its owning Epic or a human to provide that input;
    # an audit must not invent a planning instruction.
    from cascade.workspace.kickoff import (
        _graph_has_inflight_turn,
        deferred_kickoffs,
        graph_turn_owner_is_live,
        kickoff_turn,
    )
    from cascade.workspace.types import KickoffReason

    if graph_turn_owner_is_live(feature_id):
        return _refused(
            feature_id,
            "resume_planning_owner",
            generation,
            "live_owner",
        )
    if not _graph_has_inflight_turn(
        feature_id, "feature", root=product, feature_id=None
    ):
        return _refused(
            feature_id,
            "resume_planning_owner",
            generation,
            "no_resumable_graph_input",
        )
    with deferred_kickoffs():
        kickoff_turn(
            KickoffReason(
                "resume_inflight", feature_id, "watchdog", product
            )
        )
    return _postcheck(
        _result(
            feature_id,
            "resume_planning_owner",
            generation,
            state="pending",
            ok=False,
            acknowledgement="graph_resume_queued",
            observed_generation=observation.generation.value,
        ),
        feature_id,
        product,
    )


def restore_child_dispatch(
    task_id: str, *, feature_id: str, generation: str, root: Path
) -> dict[str, object]:
    """Restore one direct Task through dispatch or supervised recovery."""

    action = f"restore_child_dispatch:{task_id}"
    admitted = _admit_parent_action(
        feature_id, action, generation=generation, root=root
    )
    if isinstance(admitted, dict):
        return admitted
    _observation, product, _worktree = admitted

    from cascade.workspace.doc_root import read_doc_resolved

    task = read_doc_resolved(task_id, root=product)
    if task.meta.tier != "task" or task.meta.parent != feature_id:
        return _refused(feature_id, action, generation, "task_owner_changed")

    if task.meta.status in {"backlog", "ready_to_plan"}:
        from cascade.watchdog.dispatch import dispatch_task
        from cascade.war_room.serialize import dispatch_result_to_dict
        from cascade.workspace.kickoff import deferred_kickoffs

        with deferred_kickoffs():
            dispatched = dispatch_task(
                task_id, "boss", root=product, expected_parent=feature_id
            )
        payload = dispatch_result_to_dict(dispatched)
        return _postcheck(
            _result(
                feature_id,
                action,
                generation,
                state="dispatched" if dispatched.ok else "retryable",
                ok=dispatched.ok,
                task_id=task_id,
                dispatch=payload,
            ),
            feature_id,
            product,
        )

    # Active/blocked children keep their original Task delivery identity and
    # are handled by the existing Feature -> Task supervisor adapter.
    from cascade.team_supervision import supervise_child

    recovered = supervise_child(
        task_id, "recover", feature_id=feature_id, root=product
    )
    ok = bool(isinstance(recovered, Mapping) and recovered.get("ok", True))
    return _postcheck(
        _result(
            feature_id,
            action,
            generation,
            state="reconciled" if ok else "retryable",
            ok=ok,
            task_id=task_id,
            recovery=(
                dict(recovered) if isinstance(recovered, Mapping) else recovered
            ),
        ),
        feature_id,
        product,
    )


def retry_owned_publication(
    action_id: str, *, feature_id: str, generation: str, root: Path
) -> dict[str, object]:
    """Retry the exact durable branch/review action owned by this Feature."""

    admitted = _admit_owned_action(
        feature_id, action_id, generation=generation, root=root
    )
    if isinstance(admitted, dict):
        return admitted
    _observation, product, _worktree, action = admitted
    kind = action.get("action_kind")
    if kind == "integration_branch_update":
        from cascade.feature.branch_recovery import retry_integration_branch_update

        value = retry_integration_branch_update(
            action_id, feature_id=feature_id, root=product
        )
    elif kind in {"review_health", "review_rebase"}:
        from cascade.feature.review_recovery import publish_review_resolution

        value = publish_review_resolution(
            action_id, feature_id=feature_id, root=product
        )
    else:
        return _refused(
            feature_id,
            "retry_owned_publication",
            generation,
            "unsupported_owned_action",
            result_id=action_id,
        )

    state = str(value.get("recovery_state") or "retryable")
    return _postcheck(
        _result(
            feature_id,
            "retry_owned_publication",
            generation,
            result_id=action_id,
            state="reconciled" if state == "completed" else "retryable",
            ok=state == "completed",
            action_result=dict(value),
        ),
        feature_id,
        product,
    )


def publish_integration_review(
    feature_id: str, *, generation: str, root: Path
) -> dict[str, object]:
    """Publish completed local Feature work through the canonical review path."""

    admitted = _admit_parent_action(
        feature_id, "publish_integration_review", generation=generation, root=root
    )
    if isinstance(admitted, dict):
        return admitted
    _observation, product, _worktree = admitted

    from cascade.boss.rollup import try_complete_feature
    from cascade.review import review_record_for_feature

    completed = try_complete_feature(feature_id, root=product)
    review = review_record_for_feature(feature_id, root=product)
    if review is not None:
        identity = review.get("url") or review.get("number")
        return _postcheck(
            _result(
                feature_id,
                "publish_integration_review",
                generation,
                result_id=f"{feature_id}:review:{identity}",
                state="reconciled" if review.get("closed") else "review_pending",
                ok=bool(review.get("closed")),
                review_identity=identity,
                review=dict(review),
            ),
            feature_id,
            product,
        )
    return _postcheck(
        _result(
            feature_id,
            "publish_integration_review",
            generation,
            state="reconciled" if completed else "retryable",
            ok=completed,
            completed=completed,
        ),
        feature_id,
        product,
    )


def reconcile_completion_rollup(
    feature_id: str, *, generation: str, root: Path
) -> dict[str, object]:
    """Run existing review/completion reconciliation for one proven Feature."""

    admitted = _admit_parent_action(
        feature_id, "reconcile_completion_rollup", generation=generation, root=root
    )
    if isinstance(admitted, dict):
        return admitted
    _observation, product, _worktree = admitted

    from cascade.boss.rollup import feature_completed_recorded
    from cascade.completion_reconcile import reconcile_completion_with_prompts
    from cascade.review import review_record_for_feature
    from cascade.workspace.integration_worktree import merged_board

    reconciled = reconcile_completion_with_prompts(root=product)
    meta = merged_board(product).by_id.get(feature_id)
    epic_id = meta.parent if meta is not None else None
    completed = bool(
        epic_id
        and feature_completed_recorded(feature_id, epic_id, root=product)
    )
    review = review_record_for_feature(feature_id, root=product)
    state = (
        "reconciled"
        if completed
        else "review_pending"
        if review is not None and not review.get("closed")
        else "retryable"
    )
    return _postcheck(
        _result(
            feature_id,
            "reconcile_completion_rollup",
            generation,
            state=state,
            ok=completed,
            completion_result=reconciled,
            review_identity=(review or {}).get("url")
            or (review or {}).get("number"),
        ),
        feature_id,
        product,
    )


def _admit_parent_action(
    feature_id: str, action: str, *, generation: str, root: Path
) -> tuple[AuditObservation, Path, Path] | dict[str, object]:
    observation = project_audit_observation(feature_id, root=root)
    refused = _validate_observation(
        observation, feature_id, action, generation=generation
    )
    if refused is not None:
        return refused
    owner = _clean_owner_worktree(observation, feature_id, action, generation)
    if isinstance(owner, dict):
        return owner
    return observation, observation.evidence.product_repository, owner


def _admit_owned_action(
    feature_id: str, action_id: str, *, generation: str, root: Path
) -> tuple[AuditObservation, Path, Path, Mapping[str, Any]] | dict[str, object]:
    observation = project_audit_observation(feature_id, root=root)
    if observation.work_id.value != feature_id or observation.tier != "feature":
        return _refused(
            feature_id, "retry_owned_publication", generation, "owner_identity_changed"
        )
    if observation.generation.value != generation:
        return _refused(
            feature_id, "retry_owned_publication", generation, "generation_changed"
        )
    product = observation.evidence.product_repository
    action = load_action(action_id, root=product)
    owner = (action or {}).get("recovery")
    owner = owner.get("owning_team") if isinstance(owner, Mapping) else None
    if action is None or owner != {
        "kind": "feature_team",
        "work_id": feature_id,
    }:
        return _refused(
            feature_id,
            "retry_owned_publication",
            generation,
            "owned_action_unreachable",
            result_id=action_id,
        )
    # An open review is a protected human wait unless the exact owned review
    # action is the authority being retried.  A branch update cannot use that
    # action to cross the review wait.
    hard_gate = _hard_gate(
        observation,
        allow_review_pending=action.get("action_kind")
        in {"review_health", "review_rebase"},
    )
    if hard_gate is not None:
        return _refused(
            feature_id,
            "retry_owned_publication",
            generation,
            f"protected_gate:{hard_gate}",
            result_id=action_id,
        )
    references = set(observation.evidence.unresolved_references)
    if action_id not in references and action.get("recovery_state") != "completed":
        return _refused(
            feature_id,
            "retry_owned_publication",
            generation,
            "action_not_in_authoritative_evidence",
            result_id=action_id,
        )
    worktree = _clean_owner_worktree(
        observation,
        feature_id,
        "retry_owned_publication",
        generation,
        result_id=action_id,
    )
    if isinstance(worktree, dict):
        return worktree
    return observation, product, worktree, action


def _validate_observation(
    observation: AuditObservation,
    feature_id: str,
    action: str,
    *,
    generation: str,
) -> dict[str, object] | None:
    if observation.work_id.value != feature_id or observation.tier != "feature":
        return _refused(feature_id, action, generation, "owner_identity_changed")
    if observation.generation.value != generation:
        return _refused(feature_id, action, generation, "generation_changed")
    hard_gate = _hard_gate(observation)
    if hard_gate is not None:
        return _refused(
            feature_id, action, generation, f"protected_gate:{hard_gate}"
        )
    parent_action = observation.evidence.parent_action
    if (
        observation.classification != "proven_incident"
        or parent_action is None
        or parent_action.state != "executable"
        or parent_action.responsible_work_id != feature_id
        or parent_action.candidate_action != action
    ):
        return _refused(feature_id, action, generation, "incident_no_longer_matches")
    return None


def _hard_gate(
    observation: AuditObservation, *, allow_review_pending: bool = False
) -> str | None:
    for gate in observation.evidence.gates:
        normalized = gate.lower().replace("-", "_")
        if normalized == "review_pending" and allow_review_pending:
            continue
        if normalized.startswith(_HARD_GATE_PREFIXES):
            return gate
        # Unknown gates remain protected rather than being treated as consent.
        return gate
    runtime = observation.evidence.execution or {}
    if runtime.get("owner_live"):
        return "live_owner"
    if runtime.get("pending_input"):
        return "pending_input"
    return None


def _clean_owner_worktree(
    observation: AuditObservation,
    feature_id: str,
    action: str,
    generation: str,
    *,
    result_id: str | None = None,
) -> Path | dict[str, object]:
    product = locate_trunk(observation.evidence.product_repository)
    entry = get_integration_worktree(product, "feature", feature_id)
    if (
        entry is None
        or not entry.path.is_dir()
        or entry.branch != integration_branch("feature", feature_id)
    ):
        return _refused(
            feature_id,
            action,
            generation,
            "registered_feature_worktree_unreachable",
            result_id=result_id,
        )
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=entry.path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if branch.returncode != 0 or branch.stdout.strip() != entry.branch:
        return _refused(
            feature_id, action, generation, "owned_branch_changed", result_id=result_id
        )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=entry.path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if status.returncode != 0:
        return _refused(
            feature_id, action, generation, "worktree_status_unavailable", result_id=result_id
        )
    if status.stdout.strip():
        return _refused(
            feature_id, action, generation, "dirty_feature_worktree", result_id=result_id
        )
    return entry.path


def _result_id(feature_id: str, action: str, generation: str) -> str:
    digest = hashlib.sha256(f"{action}\0{generation}".encode()).hexdigest()[:24]
    return f"{feature_id}:feature_recovery:{digest}"


def _postcheck(
    result: dict[str, object], feature_id: str, root: Path
) -> dict[str, object]:
    """Attach fresh authoritative state after an adapter acknowledgement.

    The caller's reservation remains pending unless its result plus this fresh
    projection prove the requested transition.  In particular, merely queuing
    a graph turn or opening a review is not represented as terminal success.
    """

    try:
        observation = project_audit_observation(feature_id, root=root)
    except Exception as exc:
        return {
            **result,
            "postcheck": {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
            },
        }
    return {
        **result,
        "postcheck": {
            "available": True,
            "generation": observation.generation.value,
            "classification": observation.classification,
            "reason": observation.reason,
            "gates": list(observation.evidence.gates),
        },
    }


def _result(
    feature_id: str,
    action: str,
    generation: str,
    *,
    state: str,
    ok: bool,
    result_id: str | None = None,
    **details: object,
) -> dict[str, object]:
    return {
        "ok": ok,
        "feature_id": feature_id,
        "action": action,
        "generation": generation,
        "result_id": result_id or _result_id(feature_id, action, generation),
        "state": state,
        **details,
    }


def _refused(
    feature_id: str,
    action: str,
    generation: str,
    reason: str,
    *,
    result_id: str | None = None,
) -> dict[str, object]:
    return _result(
        feature_id,
        action,
        generation,
        state="refused",
        ok=False,
        result_id=result_id,
        reason=reason,
    )


register_feature_tool("resume_planning_owner", resume_planning_owner)
register_feature_tool("restore_child_dispatch", restore_child_dispatch)
register_feature_tool("retry_owned_publication", retry_owned_publication)
register_feature_tool("publish_integration_review", publish_integration_review)
register_feature_tool("reconcile_completion_rollup", reconcile_completion_rollup)


__all__ = [
    "publish_integration_review",
    "reconcile_completion_rollup",
    "restore_child_dispatch",
    "resume_planning_owner",
    "retry_owned_publication",
]
