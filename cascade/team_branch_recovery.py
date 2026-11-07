"""Owner-checked retry of a durable integration-branch update."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from cascade.task.action_recovery import (
    ActionFailure,
    ActionRecoveryError,
    load_action,
    record_owner_decision,
    record_owner_resolution,
    resume_action,
)
from cascade.workspace.branch_synchronization import _update_integration_branch
from cascade.workspace.integration_worktree import locate_trunk

TeamKind = Literal["epic_team", "feature_team"]


def retry_team_integration_branch_update(
    action_id: str,
    *,
    team_kind: TeamKind,
    team_id: str,
    root: Path,
) -> dict[str, object]:
    """Resolve ownership and retry the original branch-update action once.

    The action record remains the idempotency boundary. A team can only retry
    an integration update routed to itself, and a failed retry returns the same
    action to owner-decision state with its new conflict evidence.
    """

    trunk = locate_trunk(root)
    action = load_action(action_id, root=trunk)
    if action is None:
        raise ActionRecoveryError(f"recovery action not found: {action_id}")
    _assert_owned_integration_update(
        action, action_id=action_id, team_kind=team_kind, team_id=team_id
    )
    if action.get("recovery_state") == "completed":
        return _summary(action)

    state = action.get("recovery_state")
    if state == "awaiting_owner_decision":
        attempt = int(action.get("attempt_count") or 0) + 1
        decision_id = f"integration-branch-resolution:{action_id}:{attempt}"
        decision_owner = cast(Literal["epic_team", "feature_team"], team_kind)
        action = record_owner_decision(
            action_id,
            decision_id,
            root=trunk,
            owner=decision_owner,
            metadata={"team_id": team_id, "attempt": attempt},
        )
        action = record_owner_resolution(
            action_id,
            decision_id,
            f"resolved-in-owned-worktree:{action_id}:{attempt}",
            root=trunk,
            metadata={"team_id": team_id},
        )

    evidence = dict(dict(action.get("recovery") or {}).get("evidence") or {})
    work_id = str(evidence.get("affected_work_id") or "")

    def execute(_context: object) -> dict[str, object]:
        result = _update_integration_branch(
            work_id, root=trunk, allow_completed_recovery=True
        )
        if not result.ok:
            raise ActionFailure(
                "owner_decision",
                f"Integration branch update for {work_id} is still unresolved.",
                metadata={
                    "reason": result.reason,
                    "conflict_paths": list(result.conflict_paths),
                },
            )
        return {
            "metadata": {
                "work_id": work_id,
                "merge_sha": result.merge_sha,
                "no_op": result.no_op,
            }
        }

    return _summary(resume_action(action_id, root=trunk, execute=execute))


def _assert_owned_integration_update(
    action: dict[str, object],
    *,
    action_id: str,
    team_kind: TeamKind,
    team_id: str,
) -> None:
    if action.get("action_kind") != "integration_branch_update":
        raise PermissionError("recovery action is not an integration branch update")
    recovery = action.get("recovery")
    if not isinstance(recovery, dict):
        raise PermissionError("recovery action has no owning team")
    owner = recovery.get("owning_team")
    if owner != {"kind": team_kind, "work_id": team_id}:
        raise PermissionError("recovery action belongs to a different team")
    evidence = recovery.get("evidence")
    if not isinstance(evidence, dict):
        raise ActionRecoveryError("recovery action is missing branch-update evidence")
    work_id = evidence.get("affected_work_id")
    if not isinstance(work_id, str) or action_id != f"{work_id}:integration_branch_update":
        raise ActionRecoveryError("recovery action identity does not match its work item")


def _summary(action: dict[str, object]) -> dict[str, object]:
    return {
        "action_id": action.get("action_id"),
        "recovery_state": action.get("recovery_state"),
        "attempt_count": action.get("attempt_count"),
        "failure_classification": action.get("failure_classification"),
    }
