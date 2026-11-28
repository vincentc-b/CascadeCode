"""Owner-checked publication of a review conflict resolved in a team worktree."""

from __future__ import annotations

import subprocess
import tomllib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping

from cascade.resolution_actions import resolution_action
from cascade.review_rebase import (
    ReviewRebaseExecution,
    check_and_publish_review_rebase,
    prepare_review_rebase_turn,
)
from cascade.task.action_recovery import (
    ActionFailure,
    create_or_load_action,
    load_action,
    record_owner_decision,
    record_owner_resolution,
    resume_action,
    admit_review_publication_generation,
)
from cascade.team_branch_recovery import retry_team_integration_branch_update
from cascade.task.incident_budget import (
    POLICY_ID,
    POLICY_VERSION,
    bind_incident_budget,
    read_incident_budget,
)
from cascade.review_validation import (
    review_validation_environment,
    reserve_review_validation,
    settle_interrupted_review_validation,
    settle_unused_review_validation,
)
from cascade.workspace.integration_worktree import locate_trunk

TeamKind = Literal["epic_team", "feature_team"]


def _git(worktree: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(worktree: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=worktree,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).returncode
        == 0
    )


def _dirty_paths(worktree: Path) -> tuple[str, ...]:
    status = _git(worktree, "status", "--porcelain", "--untracked-files=all") or ""
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1]
        if not path.startswith(".cascade/"):
            paths.append(path)
    return tuple(paths)


def _authorization(
    action_id: str, *, team_kind: TeamKind, team_id: str, trunk: Path
) -> tuple[Path, str, str, tuple[str, str]]:
    admitted = resolution_action(action_id, root=trunk)
    if not isinstance(admitted, Mapping) or admitted.get("status") != "mutation_ready":
        raise PermissionError("review resolution is not mutation-ready")
    handoff, request = admitted.get("handoff"), admitted.get("request")
    if not isinstance(handoff, Mapping) or not isinstance(request, Mapping):
        raise PermissionError("review resolution metadata is unavailable")
    expected_team = f"{'epic' if team_kind == 'epic_team' else 'feature'}:{team_id}"
    if handoff.get("accountable_team") != expected_team:
        raise PermissionError("review resolution belongs to a different team")
    worktree_raw = handoff.get("worktree")
    refs, shas = handoff.get("authorized_refs"), handoff.get("observed_shas")
    if (
        not isinstance(worktree_raw, str)
        or not isinstance(refs, list)
        or len(refs) != 2
        or not isinstance(shas, list)
        or len(shas) != 2
        or not all(isinstance(item, str) and item for item in [*refs, *shas])
    ):
        raise PermissionError("review resolution authorization is invalid")
    return Path(worktree_raw).resolve(), refs[0], refs[1], (shas[0], shas[1])


def local_review_resolution_ready(
    action_id: str, *, team_kind: TeamKind, team_id: str, root: Path
) -> bool:
    """Return true only when the clean owned branch contains both observed heads."""

    trunk = locate_trunk(root)
    worktree, source_ref, _target_ref, heads = _authorization(
        action_id, team_kind=team_kind, team_id=team_id, trunk=trunk
    )
    if _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") != source_ref:
        return False
    if _dirty_paths(worktree):
        return False
    local_head = _git(worktree, "rev-parse", "--verify", "HEAD^{commit}")
    return bool(
        local_head
        and _is_ancestor(worktree, heads[0], local_head)
        and _is_ancestor(worktree, heads[1], local_head)
    )


def publish_team_review_resolution(
    action_id: str, *, team_kind: TeamKind, team_id: str, root: Path
) -> dict[str, object]:
    """Test and lease-publish a team-owned branch after its conflict is resolved."""

    trunk = locate_trunk(root)
    existing = load_action(action_id, root=trunk)
    if existing is not None and existing.get("action_kind") == "review_health":
        from cascade.review_health import retry_review_health

        return retry_review_health(
            action_id, team_kind=team_kind, team_id=team_id, root=trunk
        )
    worktree, source_ref, target_ref, heads = _authorization(
        action_id, team_kind=team_kind, team_id=team_id, trunk=trunk
    )
    if not local_review_resolution_ready(
        action_id, team_kind=team_kind, team_id=team_id, root=trunk
    ):
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": "local_resolution_not_ready",
        }

    action = load_action(action_id, root=trunk)
    if action is None:
        action = create_or_load_action(
            action_id,
            "review_rebase",
            root=trunk,
            attempt_bound=3,
            owning_team={"kind": team_kind, "work_id": team_id},
            evidence={
                "affected_work_id": team_id,
                "source_ref": source_ref,
                "target_ref": target_ref,
                "observed_source_head": heads[0],
                "observed_target_head": heads[1],
            },
        )
    else:
        recovery = action.get("recovery")
        owner = recovery.get("owning_team") if isinstance(recovery, Mapping) else None
        if owner != {"kind": team_kind, "work_id": team_id}:
            raise PermissionError("durable review recovery belongs to a different team")
        # Replay reports the result of this completed action, not a new
        # publication against moving review heads. Fresh work needs admission.
        if action.get("recovery_state") == "completed":
            return {
                "action_id": action_id,
                "recovery_state": "completed",
                "attempt_count": action.get("attempt_count"),
            }

    existing_budget = read_incident_budget(action_id, root=trunk)
    next_eligible = (
        existing_budget.get("next_eligible_at")
        if isinstance(existing_budget, Mapping)
        else None
    )
    if isinstance(next_eligible, str):
        try:
            backoff_until = datetime.fromisoformat(next_eligible).astimezone(timezone.utc)
        except ValueError:
            backoff_until = None
        if backoff_until is not None and datetime.now(timezone.utc) < backoff_until:
            return {
                "action_id": action_id,
                "recovery_state": action.get("recovery_state"),
                "attempt_count": action.get("attempt_count"),
                "reason": "validation_budget_transient_backoff",
                "incident_id": action_id,
                "claim_id": f"review-publication:{action_id}",
            }

    # A clean local merge is not a new owner decision on every health poll.
    # Bind retries to the actual resolution and the operator-owned check policy.
    from cascade.review_rebase import validation_command
    from cascade.review_validation import (
        ReviewValidationAdmissionError,
        approved_review_validation_profile,
        exact_review_identity,
        inspect_exact_validation_material,
        match_review_validation_receipt,
        preflight_review_validation,
    )

    validation_profile = None
    try:
        from cascade.validation_command import review_validation_command

        local_head_for_profile = _git(
            worktree, "rev-parse", "--verify", "HEAD^{commit}"
        )
        modified_for_profile = tuple(
            path
            for path in (
                _git(
                    worktree,
                    "diff",
                    "--name-only",
                    f"{heads[1]}..{local_head_for_profile}",
                )
                or ""
            ).splitlines()
            if path
        )
        approved_command = validation_command(trunk)
        validation_profile = approved_review_validation_profile(
            trunk,
            command=review_validation_command(
                trunk,
                worktree,
                modified_for_profile,
                configured_command=approved_command,
            ),
        )
        preflight_review_validation(validation_profile, cwd=worktree)
    except (ReviewValidationAdmissionError, ValueError) as exc:
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": "validation_profile_infeasible",
            "detail": str(exc),
            "validation_profile": (
                validation_profile.profile_id
                if validation_profile is not None
                else None
            ),
        }

    publication_preflight = prepare_review_rebase_turn(action_id, root=trunk)
    if publication_preflight.turn is None:
        blocker = publication_preflight.blocker
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": blocker.code if blocker is not None else "preflight_failed",
            "detail": blocker.message if blocker is not None else "review preflight failed",
        }
    admitted_turn = publication_preflight.turn
    local_head = _git(worktree, "rev-parse", "--verify", "HEAD^{commit}")
    durable_review = resolution_action(action_id, root=trunk)
    request = durable_review.get("request") if isinstance(durable_review, Mapping) else None
    if not isinstance(request, Mapping) or not isinstance(local_head, str):
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": "review_identity_unavailable",
        }
    review_fields = exact_review_identity(
        action_id,
        admitted_turn.review_id,
        source_ref,
        target_ref,
        admitted_turn.observed_source_sha,
        admitted_turn.observed_target_sha,
        request,
    )
    if review_fields is None:
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": "review_identity_unavailable",
        }
    inspection = inspect_exact_validation_material(
        worktree,
        local_head,
        admitted_turn.observed_target_sha,
        profile=validation_profile,
        review_identity=review_fields,
    )
    if inspection.material is None:
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": inspection.reason or "candidate_identity_unavailable",
            "detail": inspection.owner_action,
        }
    validation_material = inspection.material

    generation = {
        "source_head": local_head,
        "source_tree": _git(worktree, "rev-parse", "HEAD^{tree}"),
        "observed_heads": [
            admitted_turn.observed_source_sha,
            admitted_turn.observed_target_sha,
        ],
        "validation_command": list(validation_profile.command),
        "validation_timeout_seconds": validation_profile.timeout_seconds,
        "validation_profile": {
            "id": validation_profile.profile_id,
            "coverage_class": validation_profile.coverage_class,
            "policy_owner": validation_profile.policy_owner,
            "approval_version": validation_profile.approval_version,
            "attempt_budget": validation_profile.attempt_budget,
        },
        "budget_policy": {"id": POLICY_ID, "version": POLICY_VERSION},
        "environment_revision": review_validation_environment(),
        "exact_validation_material": validation_material.identity,
        "exact_validation_fingerprint": validation_material.fingerprint,
    }
    config_path = trunk / "cascade.toml"
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    policy = config.get("validation", {})
    action, admitted_generation = admit_review_publication_generation(
        action_id,
        generation,
        root=trunk,
        allow_legacy_policy_upgrade=(
            "review_command" in policy or "review_timeout_seconds" in policy
        ),
    )
    if not admitted_generation:
        return {
            "action_id": action_id,
            "recovery_state": action.get("recovery_state"),
            "attempt_count": action.get("attempt_count"),
            "reason": None
            if action.get("recovery_state") == "completed"
            else "publication_generation_unchanged_or_blocked",
        }

    # Bind material evidence before claiming an action attempt.  This makes a
    # first validator distinguishable from unknown legacy consumption and lets
    # the cumulative gate refuse a repeated request without spawning anything.
    action = load_action(action_id, root=trunk) or action
    incident = action.get("incident") if isinstance(action, Mapping) else None
    incident_generation = (
        incident.get("authoritative_generation")
        if isinstance(incident, Mapping)
        else None
    )
    if not isinstance(incident_generation, str):
        return {
            "action_id": action_id,
            "recovery_state": "awaiting_owner_decision",
            "reason": "canonical_incident_generation_missing",
        }
    budget = bind_incident_budget(
        action_id,
        action_id,
        incident_generation,
        {"policy_version": POLICY_VERSION},
        root=trunk,
    )

    generation_fingerprint = hashlib.sha256(
        json.dumps(generation, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    validator_operations = [
        operation_id
        for operation_id in (budget.get("operations") or {})
        if str(operation_id).startswith(f"review-validator:{action_id}:")
    ]
    operation_id = (
        f"review-validator:{action_id}:{generation_fingerprint}:"
        f"{len(validator_operations) + 1}"
    )
    claim_id = f"review-publication:{action_id}"
    receipt_state, reusable_receipt = match_review_validation_receipt(
        action_id, validation_material, root=trunk
    )
    validation_operation = None
    if receipt_state == "same_material_fenced":
        return {
            "action_id": action_id,
            "recovery_state": action.get("recovery_state"),
            "attempt_count": action.get("attempt_count"),
            "reason": "validation_budget_deterministic_material_unchanged",
            "incident_id": action_id,
            "claim_id": claim_id,
            "operation_id": reusable_receipt.get("operation_id") if reusable_receipt else None,
        }
    if receipt_state == "unavailable":
        return {
            "action_id": action_id,
            "recovery_state": action.get("recovery_state"),
            "attempt_count": action.get("attempt_count"),
            "reason": "validation_receipt_unavailable",
            "incident_id": action_id,
            "claim_id": claim_id,
            "operation_id": reusable_receipt.get("operation_id") if reusable_receipt else None,
        }
    if receipt_state == "matching_green" and reusable_receipt is not None:
        operation_id = str(reusable_receipt["operation_id"])
    else:
        budget_decision, validation_operation = reserve_review_validation(
            action_id,
            claim_id,
            operation_id,
            root=trunk,
            timeout=float(generation["validation_timeout_seconds"]),
            environment_revision=dict(generation["environment_revision"]),
            profile=validation_profile,
            material=validation_material,
        )
        reusable_receipt = None
    if receipt_state != "matching_green" and validation_operation is None:
        return {
            "action_id": action_id,
            "recovery_state": action.get("recovery_state"),
            "attempt_count": action.get("attempt_count"),
            "reason": f"validation_budget_{budget_decision.reason}",
            "incident_id": action_id,
            "claim_id": claim_id,
            "operation_id": operation_id,
        }

    if action.get("recovery_state") == "awaiting_owner_decision":
        decisions = [
            item
            for item in action.get("owner_decisions", [])
            if isinstance(item, Mapping) and item.get("state") != "resolved"
        ]
        if not decisions:
            fingerprint = hashlib.sha256(
                json.dumps(generation, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            decision_id = f"review-resolution:{action_id}:generation:{fingerprint}"
            action = record_owner_decision(
                action_id,
                decision_id,
                root=trunk,
                owner=team_kind,
                metadata={"team_id": team_id, "publication_generation": generation},
            )
            decisions = [
                item
                for item in action.get("owner_decisions", [])
                if isinstance(item, Mapping) and item.get("state") != "resolved"
            ]
        for decision in decisions:
            decision_id = decision.get("decision_id")
            if decision.get("owner") != team_kind or not isinstance(decision_id, str):
                if validation_operation is not None:
                    settle_unused_review_validation(validation_operation)
                raise PermissionError(
                    "review recovery has an unresolved decision for another team"
                )
            action = record_owner_resolution(
                action_id,
                decision_id,
                f"resolved-in-owned-worktree:{action_id}",
                root=trunk,
                metadata={"team_id": team_id, "publication_generation": generation},
            )

    validation_consumed = False
    validation_started = False

    def execute(_context: object) -> dict[str, object]:
        nonlocal validation_consumed, validation_started
        preflight = prepare_review_rebase_turn(action_id, root=trunk)
        if preflight.turn is None:
            blocker = preflight.blocker
            raise ActionFailure(
                "owner_decision",
                blocker.message if blocker is not None else "review preflight failed",
                metadata={
                    "reason": blocker.code
                    if blocker is not None
                    else "preflight_failed",
                    "publication_generation": generation,
                },
            )
        turn = preflight.turn
        local_head = _git(worktree, "rev-parse", "--verify", "HEAD^{commit}")
        if (
            not local_head
            or local_head != generation["source_head"]
            or not all(_is_ancestor(worktree, head, local_head) for head in heads)
        ):
            raise ActionFailure(
                "owner_decision",
                "The owned branch no longer contains both admitted review heads.",
                metadata={
                    "reason": "local_resolution_not_ready",
                    "publication_generation": generation,
                },
            )
        modified = tuple(
            path
            for path in (
                _git(worktree, "diff", "--name-only", f"{heads[1]}..{local_head}") or ""
            ).splitlines()
            if path
        )
        validation_started = reusable_receipt is None
        publication = check_and_publish_review_rebase(
            turn,
            ReviewRebaseExecution(True, local_head, modified),
            validation_operation=validation_operation,
            validation_material=validation_material,
            reusable_receipt=reusable_receipt,
        )
        current_budget = read_incident_budget(action_id, root=trunk) or {}
        receipt = (current_budget.get("operations") or {}).get(operation_id) or {}
        validation_consumed = (
            reusable_receipt is not None or receipt.get("state") == "settled"
        )
        if not publication.published:
            blocker = publication.blocker
            raise ActionFailure(
                "owner_decision",
                blocker.message if blocker is not None else "review publication failed",
                metadata={
                    "reason": blocker.code
                    if blocker is not None
                    else "publication_failed",
                    "publication_generation": generation,
                    "checks": [
                        {
                            "command": list(check.command),
                            "returncode": check.returncode,
                            "stdout": check.stdout[-8192:],
                            "stderr": check.stderr[-8192:],
                        }
                        for check in publication.checks
                    ],
                },
            )
        if team_kind == "feature_team" and validation_material is not None:
            from cascade.review import record_exact_candidate_proof

            if not record_exact_candidate_proof(
                team_id,
                action_id,
                operation_id,
                validation_material,
                root=trunk,
            ):
                raise ActionFailure(
                    "owner_decision",
                    "The exact candidate proof could not be bound to the current review.",
                    metadata={
                        "reason": "review_candidate_proof_changed",
                        "publication_generation": generation,
                    },
                )
        return {
            "metadata": {
                "published_head": publication.source_head,
                "review_id": turn.review_id,
                "source_ref": source_ref,
                "publication_generation": generation,
                "checks": [
                    {
                        "command": list(check.command),
                        "returncode": check.returncode,
                        "stdout": check.stdout[-8192:],
                        "stderr": check.stderr[-8192:],
                    }
                    for check in publication.checks
                ],
            }
        }

    try:
        completed = resume_action(action_id, root=trunk, execute=execute)
    finally:
        if not validation_consumed:
            current_budget = read_incident_budget(action_id, root=trunk) or {}
            receipt = (current_budget.get("operations") or {}).get(operation_id) or {}
            if validation_operation is not None and receipt.get("state") == "reserved":
                if validation_started:
                    settle_interrupted_review_validation(validation_operation)
                else:
                    settle_unused_review_validation(validation_operation)
    result = {
        "action_id": action_id,
        "recovery_state": completed.get("recovery_state"),
        "attempt_count": completed.get("attempt_count"),
        "failure_classification": completed.get("failure_classification"),
        "incident_id": action_id,
        "claim_id": claim_id,
        "operation_id": operation_id,
    }
    if completed.get("recovery_state") not in {"completed", "running"}:
        from cascade.task.action_recovery import capture_and_route_action_failure

        latest = (completed.get("attempts") or [{}])[-1]
        details = latest.get("completion_metadata") or {}
        result["reason"] = details.get("reason") or "review_publication_failed"
        capture_and_route_action_failure(
            action_id,
            "review_rebase",
            affected_work_id=team_id,
            intended_target_ref=target_ref,
            root=trunk,
            failure_code=str(result["reason"]),
            safe_summary=(
                f"Review publication failed: {result['reason']}. Correct the owned branch or validation, "
                f"then call publish_review_resolution with action_id {action_id}."
            ),
            owning_team={"kind": team_kind, "work_id": team_id},
            evidence={"source_ref": source_ref, "target_ref": target_ref},
        )
    # A failed Update Branch action and the later review-health action can
    # describe the same conflict episode. Once the reviewed source contains
    # the target and is published, reconcile that older durable warning too.
    integration_action_id = f"{team_id}:integration_branch_update"
    integration_action = load_action(integration_action_id, root=trunk)
    if (
        completed.get("recovery_state") == "completed"
        and integration_action is not None
        and integration_action.get("recovery_state") != "completed"
    ):
        result["integration_recovery"] = retry_team_integration_branch_update(
            integration_action_id,
            team_kind=team_kind,
            team_id=team_id,
            root=trunk,
        )
    return result
