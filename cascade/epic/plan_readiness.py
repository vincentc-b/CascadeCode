"""Authoritative epic-plan readiness for sign-off, approval, and read models (feat_015_001)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.types import BoardIndex
from cascade.dependency_evaluation import DependencyOutcome
from cascade.dependency_explanations import dependency_outcome_explanation
from cascade.dependency_projection import (
    DependencyStatusProjection,
    project_dependency_evaluation,
)
from cascade.epic.planning_signoffs import (
    PlanSignOffError,
    PlanningRole,
    canonical_plan_revision,
    current_valid_sign_offs,
    unresolved_canonical_open_questions,
)
from cascade.planning_action_dependencies import evaluate_action_dependencies
from cascade.workspace.integration_worktree import merged_board

PlanningStatus = Literal["planning", "ready_for_review"]
PlanReadinessBlockerCategory = Literal["dependency", "plan_readiness"]


class PlanNotReadyForApproval(PlanSignOffError):
    """Epic plan cannot be approved until readiness conditions are met."""


@dataclass(frozen=True, slots=True)
class PlanReadinessBlocker:
    code: str
    category: PlanReadinessBlockerCategory
    explanation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "category": self.category,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class EpicPlanReadiness:
    status: PlanningStatus
    plan_revision: str | None
    sign_offs: dict[PlanningRole, dict[str, object]]
    can_approve_plan: bool
    approve_disabled_reason: str | None
    approve_disabled_explanation: str | None
    dependency_status: DependencyStatusProjection
    blockers: tuple[PlanReadinessBlocker, ...]
    dependency_blockers: tuple[dict[str, object], ...] = ()


def compute_epic_plan_readiness(
    epic_id: str,
    *,
    root: Path,
    board: BoardIndex | None = None,
) -> EpicPlanReadiness | None:
    """Return readiness for an active, unapproved epic; ``None`` when not applicable."""

    board = board or merged_board(root)
    snapshot_meta = board.by_id.get(epic_id)
    dependency_evidence = evaluate_action_dependencies(epic_id, root=root)
    # Prefer the owner read at the dependency boundary. Keeping the supplied
    # snapshot only as a fallback lets an unavailable refresh be represented as
    # a dependency blocker instead of making an otherwise visible epic vanish.
    meta = dependency_evidence.owner or snapshot_meta
    if meta is None or meta.tier != "epic":
        return None
    if meta.plan_approved_at is not None:
        return None
    if meta.path.parent.name != "2_active":
        return None

    revision = canonical_plan_revision(epic_id, root=root, meta=meta)
    open_questions = unresolved_canonical_open_questions(epic_id, root=root)
    valid = (
        current_valid_sign_offs(epic_id, root=root, plan_revision=revision)
        if revision is not None
        else {}
    )

    sign_offs = {role: row.to_dict() for role, row in valid.items()}
    missing_roles = _missing_roles(valid)

    from cascade.epic.dependency_evidence import compute_dependency_readiness

    dependency_readiness = compute_dependency_readiness(epic_id, root=root)
    dependency_blockers = tuple(row.to_dict() for row in dependency_readiness.blockers)
    dependency_outcome = dependency_evidence.outcome
    dependency_status = project_dependency_evaluation(
        epic_id, dependency_evidence.evaluation
    )
    blockers = _plan_readiness_blockers(
        dependency_outcome=dependency_outcome,
        open_questions=bool(open_questions),
        revision_available=revision is not None,
        missing_roles=missing_roles,
    )
    if dependency_blockers:
        blockers += (
            PlanReadinessBlocker(
                code="dependencies_not_ready",
                category="dependency",
                explanation="Validate software prerequisites before approval.",
            ),
        )
    if dependency_outcome != "satisfied":
        return EpicPlanReadiness(
            status="planning",
            plan_revision=revision,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason=dependency_outcome,
            approve_disabled_explanation=dependency_outcome_explanation(
                dependency_outcome
            ),
            dependency_status=dependency_status,
            blockers=blockers,
            dependency_blockers=dependency_blockers,
        )

    if open_questions:
        return EpicPlanReadiness(
            status="planning",
            plan_revision=revision,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason="unresolved_open_questions",
            approve_disabled_explanation="Resolve all open questions before approval.",
            dependency_status=dependency_status,
            blockers=blockers,
            dependency_blockers=dependency_blockers,
        )

    if revision is None:
        return EpicPlanReadiness(
            status="planning",
            plan_revision=None,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason="canonical_revision_unavailable",
            approve_disabled_explanation=(
                "Plan revision is unavailable; refresh and try again."
            ),
            dependency_status=dependency_status,
            blockers=blockers,
            dependency_blockers=dependency_blockers,
        )

    if dependency_blockers:
        return EpicPlanReadiness(
            status="planning",
            plan_revision=revision,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason="dependencies_not_ready",
            approve_disabled_explanation="Validate software prerequisites before approval.",
            dependency_status=dependency_status,
            blockers=blockers,
            dependency_blockers=dependency_blockers,
        )

    if missing_roles:
        reason = _missing_role_reason(missing_roles[0])
        return EpicPlanReadiness(
            status="planning",
            plan_revision=revision,
            sign_offs=sign_offs,
            can_approve_plan=False,
            approve_disabled_reason=reason,
            approve_disabled_explanation=_readiness_explanation(reason),
            dependency_status=dependency_status,
            blockers=blockers,
            dependency_blockers=dependency_blockers,
        )

    return EpicPlanReadiness(
        status="ready_for_review",
        plan_revision=revision,
        sign_offs=sign_offs,
        can_approve_plan=True,
        approve_disabled_reason=None,
        approve_disabled_explanation=None,
        dependency_status=dependency_status,
        blockers=blockers,
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
        "dependency_blockers": list(readiness.dependency_blockers),
        "approve_disabled_explanation": readiness.approve_disabled_explanation,
        "dependency_status": readiness.dependency_status.to_dict(),
        "blockers": [blocker.to_dict() for blocker in readiness.blockers],
    }


_PLANNING_ROLE_ORDER: tuple[PlanningRole, ...] = ("epic_manager", "epic_architect")


def _missing_roles(valid: dict[PlanningRole, object]) -> list[PlanningRole]:
    return [role for role in _PLANNING_ROLE_ORDER if role not in valid]


def _missing_role_reason(role: PlanningRole) -> str:
    if role == "epic_manager":
        return "missing_epic_manager_sign_off"
    return "missing_epic_architect_sign_off"


def _readiness_explanation(reason: str) -> str:
    if reason == "missing_epic_manager_sign_off":
        return "Epic Manager must sign off on the current plan revision."
    return "Epic Architect must sign off on the current plan revision."


def _plan_readiness_blockers(
    *,
    dependency_outcome: DependencyOutcome,
    open_questions: bool,
    revision_available: bool,
    missing_roles: list[PlanningRole],
) -> tuple[PlanReadinessBlocker, ...]:
    """Return every blocker without folding plan/review state into dependency state."""

    blockers: list[PlanReadinessBlocker] = []
    if dependency_outcome != "satisfied":
        blockers.append(
            PlanReadinessBlocker(
                code=dependency_outcome,
                category="dependency",
                explanation=dependency_outcome_explanation(dependency_outcome),
            )
        )
    if open_questions:
        blockers.append(
            PlanReadinessBlocker(
                code="unresolved_open_questions",
                category="plan_readiness",
                explanation="Resolve all open questions before approval.",
            )
        )
    if not revision_available:
        blockers.append(
            PlanReadinessBlocker(
                code="canonical_revision_unavailable",
                category="plan_readiness",
                explanation="Plan revision is unavailable; refresh and try again.",
            )
        )
    for role in missing_roles:
        reason = _missing_role_reason(role)
        blockers.append(
            PlanReadinessBlocker(
                code=reason,
                category="plan_readiness",
                explanation=_readiness_explanation(reason),
            )
        )
    return tuple(blockers)
