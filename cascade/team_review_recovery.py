"""Owner-checked publication of a review conflict resolved in a team worktree."""

from __future__ import annotations

import subprocess
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
)
from cascade.team_branch_recovery import retry_team_integration_branch_update
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

    if action.get("recovery_state") == "awaiting_owner_decision":
        decisions = [
            item
            for item in action.get("owner_decisions", [])
            if isinstance(item, Mapping) and item.get("state") != "resolved"
        ]
        if not decisions:
            decision_id = f"review-resolution:{action_id}:attempt:{int(action.get('attempt_count') or 0) + 1}"
            action = record_owner_decision(
                action_id,
                decision_id,
                root=trunk,
                owner=team_kind,
                metadata={"team_id": team_id},
            )
            decisions = [
                item
                for item in action.get("owner_decisions", [])
                if isinstance(item, Mapping) and item.get("state") != "resolved"
            ]
        for decision in decisions:
            decision_id = decision.get("decision_id")
            if decision.get("owner") != team_kind or not isinstance(decision_id, str):
                raise PermissionError(
                    "review recovery has an unresolved decision for another team"
                )
            action = record_owner_resolution(
                action_id,
                decision_id,
                f"resolved-in-owned-worktree:{action_id}",
                root=trunk,
                metadata={"team_id": team_id},
            )

    def execute(_context: object) -> dict[str, object]:
        preflight = prepare_review_rebase_turn(action_id, root=trunk)
        if preflight.turn is None:
            blocker = preflight.blocker
            raise ActionFailure(
                "owner_decision",
                blocker.message if blocker is not None else "review preflight failed",
                metadata={
                    "reason": blocker.code
                    if blocker is not None
                    else "preflight_failed"
                },
            )
        turn = preflight.turn
        local_head = _git(worktree, "rev-parse", "--verify", "HEAD^{commit}")
        if not local_head or not all(
            _is_ancestor(worktree, head, local_head) for head in heads
        ):
            raise ActionFailure(
                "owner_decision",
                "The owned branch no longer contains both admitted review heads.",
                metadata={"reason": "local_resolution_not_ready"},
            )
        modified = tuple(
            path
            for path in (
                _git(worktree, "diff", "--name-only", f"{heads[1]}..{local_head}") or ""
            ).splitlines()
            if path
        )
        publication = check_and_publish_review_rebase(
            turn, ReviewRebaseExecution(True, local_head, modified)
        )
        if not publication.published:
            blocker = publication.blocker
            raise ActionFailure(
                "owner_decision",
                blocker.message if blocker is not None else "review publication failed",
                metadata={
                    "reason": blocker.code
                    if blocker is not None
                    else "publication_failed"
                },
            )
        return {
            "metadata": {
                "published_head": publication.source_head,
                "review_id": turn.review_id,
                "source_ref": source_ref,
            }
        }

    completed = resume_action(action_id, root=trunk, execute=execute)
    result = {
        "action_id": action_id,
        "recovery_state": completed.get("recovery_state"),
        "attempt_count": completed.get("attempt_count"),
        "failure_classification": completed.get("failure_classification"),
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
