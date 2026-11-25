"""Authoritative closeout for generation-bound parent lifecycle incidents."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cascade.board.context import resolve_root
from cascade.task.action_recovery import load_action, recovery_actions
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.watchdog.reservations import verify_incident_postcheck


FAILURE_CLASS = "parent_lifecycle_mismatch"


def pending_parent_lifecycle_postchecks(root: Path) -> dict[str, str]:
    """Return unresolved typed generations without consulting live systems."""

    from cascade.watchdog.audit_projection import project_recovery_sources

    pending: dict[str, str] = {}
    for incident in project_recovery_sources(resolve_root(root)).current:
        work_id = incident.work_id
        generation = incident.authoritative_generation
        if (
            incident.failure_class == FAILURE_CLASS
            and isinstance(work_id, str)
            and isinstance(generation, str)
        ):
            pending[work_id] = generation
    return pending


def reconcile_parent_lifecycle_incident(
    task_id: str,
    generation: str,
    *,
    root: Path,
    now: datetime | None = None,
    _locked: bool = False,
) -> dict[str, Any]:
    """Re-read every owed generation fact and verify exactly one incident.

    No cached audit or War Room projection participates.  The board, action
    ledger, review registry and worktree registry remain the owning stores.
    """

    repo = resolve_root(root)
    incident = _incident(task_id, generation, repo)
    if incident is None:
        return _pending("incident_generation_missing")
    evidence = incident.get("evidence")
    result = incident.get("result")
    if not isinstance(evidence, Mapping) or not isinstance(result, Mapping):
        return _pending("incident_evidence_missing")
    adapter = result.get("adapter_result")
    parent_evidence = evidence.get("parent_lifecycle_evidence")
    if not isinstance(adapter, Mapping) or not isinstance(parent_evidence, Mapping):
        return _pending("repair_execution_unproven")
    if adapter.get("executed") is not True:
        return _pending("repair_execution_unproven")

    feature_id = evidence.get("feature_id")
    acknowledgement = adapter.get("acknowledgement")
    acknowledgement = (
        acknowledgement if isinstance(acknowledgement, Mapping) else {}
    )
    repair_generation = adapter.get("generation")
    if repair_generation is None:
        repair_generation = acknowledgement.get("repair_generation")
    repair_action_id = adapter.get("action_id")
    if repair_action_id is None:
        repair_action_id = acknowledgement.get("repair_action_id")
    if (
        not isinstance(feature_id, str)
        or type(repair_generation) is not int
        or not isinstance(repair_action_id, str)
    ):
        return _pending("repair_identity_missing")

    # Keep the local lifecycle snapshot coherent while reading the stores that
    # closeout itself updates.  This path performs no provider or forge calls.
    with task_lifecycle_lock(root=repo):
        from cascade.feature.repair import feature_repair_actions
        from cascade.review import review_enabled, review_record_for_feature
        from cascade.task.execution import execution_lease_is_live
        from cascade.watchdog.capabilities import default_capability_registry
        from cascade.workspace.integration_worktree import (
            get_integration_worktree,
            merged_board,
            resolve_mutation_owner,
        )
        from cascade.workspace.runtime_identity import (
            verify_current_loaded_runtime_identity,
        )
        from cascade.workspace.supervisor_status import read_supervisor_status

        board = merged_board(repo)
        task = board.by_id.get(task_id)
        feature = board.by_id.get(feature_id)
        repairs = feature_repair_actions(feature_id, root=repo)
        repair = next(
            (
                row
                for row in repairs
                if row.get("action_id") == repair_action_id
                and row.get("generation") == repair_generation
            ),
            None,
        )
        delivery = load_action(f"{task_id}:queued_merge", root=repo)
        review = review_record_for_feature(feature_id, root=repo)
        supervisor = read_supervisor_status(repo)
        runtime_identity = (
            supervisor.get("runtime_identity")
            if isinstance(supervisor, Mapping)
            else None
        )
        runtime = verify_current_loaded_runtime_identity(
            runtime_identity,
            expected_workspace_root=repo,
            expected_capability_generation=default_capability_registry().fingerprint(),
        )
        try:
            owner_root = resolve_mutation_owner(feature_id, trunk=repo).resolve()
            owner_known = owner_root.is_dir()
        except Exception:
            owner_root = None
            owner_known = False

        original_heads = parent_evidence.get("tested_heads")
        original_validation = (
            original_heads.get("validation")
            if isinstance(original_heads, Mapping)
            else None
        )
        delivery_metadata = (
            delivery.get("metadata") if isinstance(delivery, Mapping) else None
        )
        delivered_validation = (
            delivery_metadata.get("final_validation")
            if isinstance(delivery_metadata, Mapping)
            else None
        )
        review_required = review_enabled(repo)
        review_current = (
            not review_required
            and review is None
            and isinstance(repair, Mapping)
            and repair.get("phase") == "verified"
        ) or (
            isinstance(review, Mapping)
            and review.get("current_generation") == repair_generation
            and review.get("generation") == repair_generation
            and review.get("closed") is True
            and review.get("reconciliation_status") == "accepted"
            and review.get("accepted_source_head") == review.get("source_head")
            and review.get("accepted_target_head") == review.get("target_head")
            and isinstance(review.get("accepted_merge_sha"), str)
            and bool(review.get("accepted_merge_sha"))
        )
        checks = {
            "owner_registered": owner_known,
            "owner_matches": incident.get("accountable_owner")
            == f"feature_team:{feature_id}",
            "task_completed": task is not None
            and task.status == "completed"
            and task.path.parent.name == "3_completed",
            "feature_completed": feature is not None
            and feature.status == "completed"
            and feature.path.parent.name == "3_completed",
            "delivery_completed": isinstance(delivery, Mapping)
            and delivery.get("recovery_state") == "completed",
            "validation_preserved": isinstance(original_validation, Mapping)
            and delivered_validation == original_validation,
            "repair_generation_verified": isinstance(repair, Mapping)
            and repair.get("phase") == "verified",
            "review_generation_accepted": review_current,
            "loaded_runtime_current": runtime.get("state") == "current",
            "execution_lease_retired": not execution_lease_is_live(task_id, root=repo),
            "task_worktree_retired": get_integration_worktree(
                repo, "task", task_id
            )
            is None,
            "feature_worktree_retired": get_integration_worktree(
                repo, "feature", feature_id
            )
            is None,
        }

    failed = [name for name, passed in checks.items() if not passed]
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    postcheck: dict[str, Any] = {
        "verified": not failed,
        "verified_at": stamped.isoformat() if not failed else None,
        "reason": "all_generation_obligations_proven"
        if not failed
        else f"pending:{failed[0]}",
        "task_id": task_id,
        "feature_id": feature_id,
        "authoritative_generation": generation,
        "repair_action_id": repair_action_id,
        "repair_generation": repair_generation,
        "owner_root": owner_root.as_posix() if owner_root is not None else None,
        "review": (
            {
                key: review.get(key)
                for key in (
                    "current_generation",
                    "generation",
                    "action_id",
                    "publication_action_id",
                    "state",
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
        "runtime": {
            "state": runtime.get("state"),
            "reason": runtime.get("reason"),
            "authority_manifest_id": (
                runtime_identity.get("authority_manifest_id")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
            "deployment_receipt_id": (
                runtime_identity.get("deployment_receipt_id")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
            "worker_pid": (
                runtime_identity.get("worker_pid")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
            "process_start_id": (
                runtime_identity.get("process_start_id")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
            "reviewed_revision": (
                runtime_identity.get("reviewed_revision")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
            "integrated_revision": (
                runtime_identity.get("integrated_revision")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
            "capability_generation": (
                runtime_identity.get("capability_generation")
                if isinstance(runtime_identity, Mapping)
                else None
            ),
        },
        "checks": checks,
    }
    if failed:
        return postcheck
    if not _locked:
        # The first read may perform repository-backed board/owner discovery.
        # Repeat the complete fact set while holding the lifecycle fence, then
        # keep that outer re-entrant lock through the exact ledger transition.
        with task_lifecycle_lock(root=repo):
            return reconcile_parent_lifecycle_incident(
                task_id,
                generation,
                root=repo,
                now=stamped,
                _locked=True,
            )
    postcheck["verified"] = verify_incident_postcheck(
        task_id,
        FAILURE_CLASS,
        generation,
        postcheck,
        root=repo,
        now=stamped,
    )
    if postcheck["verified"] is not True:
        postcheck["verified_at"] = None
        postcheck["reason"] = "incident_generation_changed"
    return postcheck


def _incident(task_id: str, generation: str, root: Path) -> Mapping[str, Any] | None:
    for row in recovery_actions(root=root):
        value = row.get("incident")
        if (
            isinstance(value, Mapping)
            and value.get("work_id") == task_id
            and value.get("failure_class") == FAILURE_CLASS
            and value.get("authoritative_generation") == generation
        ):
            return value
    return None


def _pending(reason: str) -> dict[str, Any]:
    return {"verified": False, "verified_at": None, "reason": reason}


__all__ = [
    "pending_parent_lifecycle_postchecks",
    "reconcile_parent_lifecycle_incident",
]
