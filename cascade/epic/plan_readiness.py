"""Authoritative epic-plan readiness for sign-off, approval, and read models (feat_015_001)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.types import BoardIndex
from cascade.epic.planning_signoffs import (
    PlanSignOffError,
    PlanningRole,
    canonical_plan_revision,
    current_valid_sign_offs,
    unresolved_canonical_open_questions,
)
from cascade.workspace.integration_worktree import merged_board

PlanningStatus = Literal["planning", "ready_for_review"]


class PlanNotReadyForApproval(PlanSignOffError):
    """Epic plan cannot be approved until readiness conditions are met."""


@dataclass(frozen=True, slots=True)
class EpicPlanReadiness:
    status: PlanningStatus
    plan_revision: str | None
    sign_offs: dict[PlanningRole, dict[str, object]]
    can_approve_plan: bool
    approve_disabled_reason: str | None


def compute_epic_plan_readiness(
    epic_id: str,
    *,
    root: Path,
    board: BoardIndex | None = None,
) -> EpicPlanReadiness | None:
    """Return readiness for an active, unapproved epic; ``None`` when not applicable."""

    board = board or merged_board(root)
    meta = board.by_id.get(epic_id)
    if meta is None or meta.tier != "epic":
        return None
    if meta.plan_approved_at is not None:
        return None
    if meta.path.parent.name != "2_active":
        return None

    revision = canonical_plan_revision(epic_id, root=root)
    open_questions = unresolved_canonical_open_questions(epic_id, root=root)
    valid = current_valid_sign_offs(epic_id, root=root) if revision is not None else {}

    sign_offs = {role: row.to_dict() for role, row in valid.items()}
    missing_roles = _missing_roles(valid)

    if open_questions:
        return EpicPlanReadiness(
            status="planning",
            plan_revision=revision,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason="unresolved_open_questions",
        )

    if revision is None:
        return EpicPlanReadiness(
            status="planning",
            plan_revision=None,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason="canonical_revision_unavailable",
        )

    if missing_roles:
        reason = _missing_role_reason(missing_roles[0])
        return EpicPlanReadiness(
            status="planning",
            plan_revision=revision,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason=reason,
        )

    return EpicPlanReadiness(
        status="ready_for_review",
        plan_revision=revision,
        sign_offs=sign_offs,
        can_approve_plan=True,
        approve_disabled_reason=None,
    )


def require_epic_plan_ready_for_approval(
    epic_id: str,
    *,
    root: Path,
    board: BoardIndex | None = None,
) -> EpicPlanReadiness:
    """Raise ``PlanNotReadyForApproval`` when approval preconditions are unmet."""

    readiness = compute_epic_plan_readiness(epic_id, root=root, board=board)
    if readiness is None:
        raise PlanNotReadyForApproval(f"{epic_id} is not an active unapproved epic")
    if not readiness.can_approve_plan:
        reason = readiness.approve_disabled_reason or "not_ready_for_review"
        raise PlanNotReadyForApproval(
            f"epic plan for {epic_id} is not ready for approval ({reason})"
        )
    return readiness


def epic_plan_readiness_to_dict(readiness: EpicPlanReadiness) -> dict[str, object]:
    return {
        "status": readiness.status,
        "plan_revision": readiness.plan_revision,
        "sign_offs": dict(readiness.sign_offs),
        "can_approve_plan": readiness.can_approve_plan,
        "approve_disabled_reason": readiness.approve_disabled_reason,
    }


_PLANNING_ROLE_ORDER: tuple[PlanningRole, ...] = ("epic_manager", "epic_architect")


def _missing_roles(valid: dict[PlanningRole, object]) -> list[PlanningRole]:
    return [role for role in _PLANNING_ROLE_ORDER if role not in valid]


def _missing_role_reason(role: PlanningRole) -> str:
    if role == "epic_manager":
        return "missing_epic_manager_sign_off"
    return "missing_epic_architect_sign_off"
