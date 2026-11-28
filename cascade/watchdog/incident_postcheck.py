"""Authoritative closeout for generation-bound parent lifecycle incidents."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cascade.board.context import resolve_root
from cascade.task.action_recovery import load_action, recovery_actions
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.watchdog.reservations import verify_incident_postcheck


FAILURE_CLASS = "parent_lifecycle_mismatch"


def reconcile_open_review_repair(
    feature_id: str,
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Independently verify the current open-review repair before closeout.

    The forge read is intentionally performed before the lifecycle critical
    section.  Mutation is allowed only after the canonical action, registry
    row and evidence digest are re-read under the fence.
    """

    repo = resolve_root(root)
    from cascade.feature.repair import feature_repair_actions
    from cascade.review import review_record_for_feature

    actions = feature_repair_actions(feature_id, root=repo)
    candidates = [
        action
        for action in actions
        if action.get("repair_route") == "open_review"
        and action.get("phase") not in {"blocked", "refused", "superseded"}
    ]
    if not candidates:
        return _pending("repair_generation_missing", "restore_repair_generation")
    action = max(candidates, key=lambda row: int(row.get("generation") or 0))
    record = review_record_for_feature(feature_id, root=repo)
    if not isinstance(record, Mapping):
        return _pending("review_evidence_missing", "restore_review_registry")
    observed = _observe_repair_review(repo, action, record)
    if observed.get("verified") is not True:
        return observed
    evidence_digest = _evidence_digest(action, record, observed)

    with task_lifecycle_lock(root=repo):
        current_actions = feature_repair_actions(feature_id, root=repo)
        current = max(
            (
                row
                for row in current_actions
                if row.get("repair_route") == "open_review"
                and row.get("phase") not in {"blocked", "refused", "superseded"}
            ),
            key=lambda row: int(row.get("generation") or 0),
            default=None,
        )
        current_record = review_record_for_feature(feature_id, root=repo)
        if not isinstance(current, Mapping) or not isinstance(current_record, Mapping):
            return _pending("repair_generation_changed", "rerun_independent_postcheck")
        if _evidence_digest(current, current_record, observed) != evidence_digest:
            return _pending("repair_generation_changed", "rerun_independent_postcheck")
        if (
            _intended_target_contains(
                repo,
                str(current.get("target_ref") or ""),
                str(observed.get("target_head") or ""),
                str(observed.get("accepted_merge_sha") or ""),
            )
            is not True
        ):
            return _pending("intended_target_changed", "rerun_independent_postcheck")
        if current.get("phase") != "verified" and not _repair_owner_and_claim_current(
            repo, current
        ):
            return _pending(
                "repair_owner_or_claim_changed", "join_current_repair_owner"
            )

        stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        postcheck = {
            **observed,
            "verified": True,
            "verified_at": stamped.isoformat(),
            "reason": "current_review_repair_proven",
            "feature_id": feature_id,
            "repair_action_id": current.get("action_id"),
            "repair_generation": current.get("generation"),
            "evidence_digest": evidence_digest,
        }
        if current.get("phase") == "verified":
            return postcheck

        from cascade.feature.repair import mark_feature_repair_verified

        if not mark_feature_repair_verified(
            feature_id,
            int(current.get("generation") or 0),
            postcheck=postcheck,
            root=repo,
        ):
            return _pending("repair_generation_changed", "rerun_independent_postcheck")
        return postcheck


def _repair_owner_and_claim_current(repo: Path, action: Mapping[str, Any]) -> bool:
    """Recheck the registered mutation owner and retained incident claim."""

    from cascade.task.action_recovery import ActionRecoveryUnavailable, _read_payload
    from cascade.workspace.errors import MutationOwnerError
    from cascade.workspace.integration_worktree import resolve_mutation_owner

    try:
        owner = resolve_mutation_owner(str(action["feature_id"]), trunk=repo).resolve()
    except (KeyError, MutationOwnerError, OSError, ValueError):
        return False
    owner_fingerprint = action.get("owner_fingerprint")
    if isinstance(owner_fingerprint, str):
        expected = hashlib.sha256(
            "\0".join(
                (
                    str(repo.resolve()),
                    str(owner),
                    str(action.get("feature_id") or ""),
                    str(action.get("epic_id") or ""),
                    str(action.get("prior_document_path") or ""),
                )
            ).encode()
        ).hexdigest()
        if owner_fingerprint != expected:
            return False
    budget_id = action.get("incident_budget_id")
    if budget_id is None:
        return True
    try:
        budgets = _read_payload(repo).get("incident_budgets")
    except ActionRecoveryUnavailable:
        return False
    budget = budgets.get(budget_id) if isinstance(budgets, Mapping) else None
    if not isinstance(budget, Mapping) or budget.get("status") != "active":
        return False
    claim = budget.get("live_claim")
    return isinstance(claim, Mapping) and claim.get("claim_id") == action.get(
        "claim_id"
    )


def _observe_repair_review(
    repo: Path, action: Mapping[str, Any], record: Mapping[str, Any]
) -> dict[str, Any]:
    """Read fresh forge facts and consume already-normalized check evidence."""

    from cascade.board.errors import GitError
    from cascade.tracking import MergeRequest, merge_request_snapshot

    identity = {
        "url": action.get("review_url"),
        "forge": action.get("review_forge"),
        "source_branch": action.get("source_ref"),
        "target_branch": action.get("target_ref"),
    }
    actual = {
        "url": record.get("url") or record.get("review_url"),
        "forge": record.get("forge"),
        "source_branch": record.get("source_branch"),
        "target_branch": record.get("target_branch"),
    }
    if identity != actual or any(value in {None, ""} for value in identity.values()):
        return _pending("review_identity_changed", "restore_original_review_identity")
    if (
        record.get("current_generation") != action.get("generation")
        or record.get("generation") != action.get("generation")
        or record.get("action_id") != action.get("action_id")
        or record.get("publication_action_id") != action.get("action_id")
    ):
        return _pending(
            "review_generation_changed", "refresh_current_review_generation"
        )
    source_head = record.get("source_head")
    if not isinstance(source_head, str) or not source_head:
        return _pending("corrected_source_head_missing", "refresh_review_observation")
    try:
        snapshot = merge_request_snapshot(
            repo,
            MergeRequest(
                url=str(identity["url"]),
                number=str(record.get("number") or "") or None,
                forge=str(identity["forge"]),
                source_branch=str(identity["source_branch"]),
                target_branch=str(identity["target_branch"]),
                draft=bool(record.get("draft", False)),
            ),
        )
    except (GitError, OSError, ValueError):
        return _pending("forge_evidence_unavailable", "retry_forge_observation")
    if (
        snapshot.get("url") != identity["url"]
        or snapshot.get("source_branch") != identity["source_branch"]
        or snapshot.get("target_branch") != identity["target_branch"]
        or snapshot.get("source_revision") != source_head
    ):
        return _pending("forge_evidence_stale", "refresh_review_observation")
    target_head = snapshot.get("target_revision")
    if not isinstance(target_head, str) or not target_head:
        return _pending("target_head_unavailable", "refresh_review_observation")
    check_result = _required_checks(snapshot, source_head, target_head)
    if check_result.get("verified") is not True:
        return check_result
    if snapshot.get("state") != "merged":
        return _pending("review_acceptance_pending", "wait_for_review_acceptance")
    from cascade.review import matching_exact_result_receipt

    exact_proof = matching_exact_result_receipt(record, snapshot, root=repo)
    if exact_proof is None:
        return _pending(
            "exact_candidate_proof_unavailable", "restore_exact_validation_receipt"
        )
    accepted_identity = snapshot.get("accepted_merge_identity")
    if (
        isinstance(accepted_identity, Mapping)
        and accepted_identity.get("available") is not True
    ):
        return _pending("accepted_merge_identity_unavailable", "refresh_forge_observation")

    merge_sha = snapshot.get("merge_sha")
    if (
        record.get("closed") is not True
        or record.get("reconciliation_status") != "accepted"
        or record.get("accepted_source_head") != source_head
        or record.get("accepted_target_head") != record.get("target_head")
        or record.get("accepted_merge_sha") != merge_sha
        or not isinstance(merge_sha, str)
        or not merge_sha
    ):
        return _pending("accepted_generation_missing", "reconcile_review_acceptance")
    integrated = _intended_target_contains(
        repo, str(action["target_ref"]), target_head, merge_sha
    )
    if integrated is None:
        return _pending(
            "target_integration_evidence_unavailable",
            "retry_epic_target_observation",
        )
    if not integrated:
        return _pending(
            "intended_target_not_integrated", "integrate_review_into_epic_target"
        )
    return {
        "verified": True,
        "source_head": source_head,
        "checked_source_head": check_result["checked_source_head"],
        "target_head": target_head,
        "accepted_merge_sha": merge_sha,
        "required_check_policy": check_result["required_check_policy"],
        "required_check_results": check_result["required_check_results"],
        "forge_state": snapshot.get("state"),
    }


def _intended_target_contains(
    repo: Path, target_ref: str, target_head: str, merge_sha: str
) -> bool | None:
    """Bind the accepted object to the exact locally synchronized target head."""

    if not target_ref or not target_head or not merge_sha:
        return False
    try:
        target = subprocess.run(
            ["git", "rev-parse", "--verify", target_ref],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=5,
        )
        if target.returncode != 0 or target.stdout.strip() != target_head:
            return False
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", merge_sha, target_ref],
                cwd=repo,
                capture_output=True,
                check=False,
                timeout=5,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _required_checks(
    snapshot: Mapping[str, Any], source_head: str, target_head: str
) -> dict[str, Any]:
    """Validate one fresh normalized policy/result generation fail closed."""

    policy = snapshot.get("required_check_policy")
    results = snapshot.get("required_check_results")
    if not isinstance(policy, Mapping) or policy.get("available") is not True:
        return _pending(
            "required_check_policy_unavailable", "refresh_required_check_policy"
        )
    required = policy.get("required")
    if (
        policy.get("source_head") != source_head
        or policy.get("target_head") != target_head
        or not target_head
        or not isinstance(required, list)
        or any(not isinstance(name, str) or not name for name in required)
        or (not required and policy.get("confirmed_empty") is not True)
    ):
        return _pending("required_check_policy_stale", "refresh_required_check_policy")
    if not isinstance(results, Mapping) or results.get("available") is not True:
        return _pending(
            "required_check_results_unavailable", "refresh_required_check_results"
        )
    statuses = results.get("statuses")
    checks = results.get("checks")
    if (
        results.get("source_head") != source_head
        or results.get("target_head") != target_head
        or not isinstance(statuses, Mapping)
        or not isinstance(checks, Mapping)
    ):
        return _pending(
            "required_check_results_stale", "refresh_required_check_results"
        )
    for name in required:
        check = checks.get(name)
        generation = check.get("generation") if isinstance(check, Mapping) else None
        if (
            statuses.get(name) not in {"success", "passed"}
            or not isinstance(check, Mapping)
            or check.get("status") not in {"success", "passed"}
            or check.get("source_head") != source_head
            or generation is None
            or generation == ""
            or isinstance(generation, bool)
        ):
            return _pending("required_checks_not_green", "wait_for_required_checks")
    return {
        "verified": True,
        "checked_source_head": source_head,
        "required_check_policy": dict(policy),
        "required_check_results": dict(results),
    }


def _evidence_digest(
    action: Mapping[str, Any], record: Mapping[str, Any], observed: Mapping[str, Any]
) -> str:
    fields = {
        "action": {
            key: action.get(key)
            for key in (
                "action_id",
                "generation",
                "phase",
                "feature_id",
                "epic_id",
                "review_url",
                "review_forge",
                "source_ref",
                "target_ref",
                "claim_id",
                "claim_owner",
                "owner_fingerprint",
                "incident_budget_id",
                "reserved_task_id",
                "final_validation",
            )
        },
        "review": {
            key: record.get(key)
            for key in (
                "current_generation",
                "generation",
                "action_id",
                "publication_action_id",
                "url",
                "forge",
                "source_branch",
                "target_branch",
                "source_head",
                "target_head",
                "closed",
                "reconciliation_status",
                "accepted_source_head",
                "accepted_target_head",
                "accepted_merge_sha",
                "required_check_policy",
                "required_check_results",
            )
        },
        "observed": dict(observed),
    }
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


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
    acknowledgement = acknowledgement if isinstance(acknowledgement, Mapping) else {}
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
            "task_worktree_retired": get_integration_worktree(repo, "task", task_id)
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


def _pending(reason: str, next_prerequisite: str | None = None) -> dict[str, Any]:
    result = {"verified": False, "verified_at": None, "reason": reason}
    if next_prerequisite is not None:
        result["next_prerequisite"] = next_prerequisite
    return result


__all__ = [
    "pending_parent_lifecycle_postchecks",
    "reconcile_open_review_repair",
    "reconcile_parent_lifecycle_incident",
]
