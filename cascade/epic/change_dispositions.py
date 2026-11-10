"""Apply corrective-work and human-blocker Epic impact dispositions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_root
from cascade.board.store import read_doc
from cascade.comments.store import reply_comment
from cascade.epic.guard import EpicToolDenied
from cascade.epic.impact_decisions import EpicImpactDecision, read_epic_impact_decisions
from cascade.epic.mint import mint_feature
from cascade.epic.registry import register_epic_tool
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import locate_trunk, merged_board

CorrectivePlanningRole = Literal["epic_manager", "epic_architect"]
DispositionKind = Literal["corrective_feature", "human_blocker"]

_REQUIRED_ROLES: tuple[CorrectivePlanningRole, ...] = (
    "epic_manager",
    "epic_architect",
)
_LEDGER = Path("docs") / "_comments" / "_epic_disposition_outcomes.json"


class ImpactDispositionError(ValueError):
    """A recorded impact disposition cannot be applied safely."""


@dataclass(frozen=True)
class CorrectivePlanSignOff:
    role: CorrectivePlanningRole
    plan_revision: str
    signed_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "plan_revision": self.plan_revision,
            "signed_at": _stamp(self.signed_at),
        }

    @classmethod
    def from_dict(cls, raw: object) -> "CorrectivePlanSignOff":
        if not isinstance(raw, dict):
            raise ValueError("corrective sign-off must be an object")
        role = raw.get("role")
        if role not in _REQUIRED_ROLES:
            raise ValueError("unknown corrective planning role")
        revision = raw.get("plan_revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError("corrective plan revision is required")
        return cls(
            role=role,
            plan_revision=revision,
            signed_at=_parse_stamp(raw.get("signed_at")),
        )


@dataclass(frozen=True)
class ImpactDispositionOutcome:
    decision_id: str
    handoff_id: str
    disposition: DispositionKind
    source_feature_id: str
    root_comment_id: str
    affected_work_ids: tuple[str, ...]
    corrective_feature_id: str | None
    accepted_dependency_ids: tuple[str, ...]
    requested_human_action: str | None
    originating_thread_reply_reference: str
    applied_by: CorrectivePlanningRole
    applied_at: datetime
    sign_offs: tuple[CorrectivePlanSignOff, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "handoff_id": self.handoff_id,
            "disposition": self.disposition,
            "source_feature_id": self.source_feature_id,
            "root_comment_id": self.root_comment_id,
            "affected_work_ids": list(self.affected_work_ids),
            "corrective_feature_id": self.corrective_feature_id,
            "accepted_dependency_ids": list(self.accepted_dependency_ids),
            "requested_human_action": self.requested_human_action,
            "originating_thread_reply_reference": self.originating_thread_reply_reference,
            "applied_by": self.applied_by,
            "applied_at": _stamp(self.applied_at),
            "sign_offs": [row.to_dict() for row in self.sign_offs],
        }

    @classmethod
    def from_dict(cls, raw: object) -> "ImpactDispositionOutcome":
        if not isinstance(raw, dict):
            raise ValueError("disposition outcome must be an object")
        disposition = raw.get("disposition")
        applied_by = raw.get("applied_by")
        if disposition not in ("corrective_feature", "human_blocker"):
            raise ValueError("unknown disposition outcome")
        if applied_by not in _REQUIRED_ROLES:
            raise ValueError("unknown applying role")
        affected = raw.get("affected_work_ids")
        dependencies = raw.get("accepted_dependency_ids")
        sign_offs = raw.get("sign_offs", [])
        if not all(isinstance(value, list) for value in (affected, dependencies, sign_offs)):
            raise ValueError("disposition outcome collections must be lists")
        corrective = raw.get("corrective_feature_id")
        requested_action = raw.get("requested_human_action")
        return cls(
            decision_id=_string(raw.get("decision_id")),
            handoff_id=_string(raw.get("handoff_id")),
            disposition=disposition,
            source_feature_id=_string(raw.get("source_feature_id")),
            root_comment_id=_string(raw.get("root_comment_id")),
            affected_work_ids=tuple(_string(item) for item in affected),
            corrective_feature_id=_optional_string(corrective),
            accepted_dependency_ids=tuple(_string(item) for item in dependencies),
            requested_human_action=_optional_string(requested_action),
            originating_thread_reply_reference=_string(
                raw.get("originating_thread_reply_reference")
            ),
            applied_by=applied_by,
            applied_at=_parse_stamp(raw.get("applied_at")),
            sign_offs=tuple(CorrectivePlanSignOff.from_dict(item) for item in sign_offs),
        )


def apply_impact_disposition(
    decision_id: str,
    *,
    epic_id: str,
    root: Path,
    title: str | None = None,
    plan: str | None = None,
    requested_human_action: str | None = None,
    author: str = "epic_manager",
) -> dict[str, object]:
    """Materialize one recorded corrective feature or visible human blocker."""

    repo = locate_trunk(resolve_root(root))
    role = _role(author)
    with process_lock:
        existing = _outcome_for_decision(decision_id, root=repo)
        if existing is not None:
            _require_same_application(
                existing,
                title=title,
                plan=plan,
                requested_human_action=requested_human_action,
                root=repo,
            )
            return _outcome_view(existing, root=repo)

        decision = _require_decision(decision_id, epic_id=epic_id, root=repo)
        if decision.disposition == "corrective_feature":
            if requested_human_action is not None:
                raise ImpactDispositionError(
                    "corrective feature does not accept a human blocker action"
                )
            outcome = _apply_corrective(
                decision,
                title=title,
                plan=plan,
                author=role,
                epic_id=epic_id,
                root=repo,
            )
        elif decision.disposition == "human_blocker":
            if title is not None or plan is not None:
                raise ImpactDispositionError(
                    "human blocker does not accept a corrective plan"
                )
            outcome = _apply_human_blocker(
                decision,
                requested_human_action=requested_human_action,
                author=role,
                root=repo,
            )
        else:
            raise ImpactDispositionError(
                f"decision {decision_id} does not require corrective work or a human blocker"
            )
        rows = _read_ledger(repo)
        rows.append(outcome)
        _write_ledger(repo, rows)
        return _outcome_view(outcome, root=repo)


def sign_off_corrective_plan(
    decision_id: str,
    plan_revision: str,
    *,
    epic_id: str,
    root: Path,
    author: str,
) -> dict[str, object]:
    """Bind one Epic planning role's sign-off to the current corrective plan."""

    repo = locate_trunk(resolve_root(root))
    role = _role(author)
    with process_lock:
        decision = _require_decision(decision_id, epic_id=epic_id, root=repo)
        if decision.disposition != "corrective_feature":
            raise ImpactDispositionError("only corrective-feature plans can be signed off")
        rows = _read_ledger(repo)
        index = next(
            (index for index, row in enumerate(rows) if row.decision_id == decision_id),
            None,
        )
        if index is None or rows[index].corrective_feature_id is None:
            raise ImpactDispositionError("apply the corrective-feature disposition first")
        outcome = rows[index]
        current_revision = _corrective_revision(outcome, root=repo)
        if plan_revision != current_revision:
            raise ImpactDispositionError(
                f"stale corrective plan revision (current {current_revision})"
            )
        same = next(
            (
                row
                for row in outcome.sign_offs
                if row.role == role and row.plan_revision == plan_revision
            ),
            None,
        )
        if same is None:
            sign_offs = tuple(
                row for row in outcome.sign_offs if row.role != role
            ) + (
                CorrectivePlanSignOff(
                    role=role,
                    plan_revision=plan_revision,
                    signed_at=datetime.now(timezone.utc),
                ),
            )
            outcome = replace(outcome, sign_offs=sign_offs)
            rows[index] = outcome
            _write_ledger(repo, rows)
        return _outcome_view(outcome, root=repo)


def read_impact_disposition_outcomes(
    *, root: Path, decision_id: str | None = None
) -> tuple[ImpactDispositionOutcome, ...]:
    repo = locate_trunk(resolve_root(root))
    with process_lock:
        rows = _read_ledger(repo)
    if decision_id is not None:
        rows = [row for row in rows if row.decision_id == decision_id]
    return tuple(rows)


def require_corrective_feature_ready_for_approval(feature_id: str, *, root: Path) -> None:
    """Require current-revision dual sign-off for a corrective feature only."""

    repo = locate_trunk(resolve_root(root))
    outcome = next(
        (
            row
            for row in _read_ledger(repo)
            if row.corrective_feature_id == feature_id
        ),
        None,
    )
    if outcome is None:
        return
    revision = _corrective_revision(outcome, root=repo)
    signed_roles = {
        row.role for row in outcome.sign_offs if row.plan_revision == revision
    }
    missing = [role for role in _REQUIRED_ROLES if role not in signed_roles]
    if missing:
        raise ImpactDispositionError(
            f"corrective feature {feature_id} requires current-revision sign-off from "
            + ", ".join(missing)
        )


def _apply_corrective(
    decision: EpicImpactDecision,
    *,
    title: str | None,
    plan: str | None,
    author: CorrectivePlanningRole,
    epic_id: str,
    root: Path,
) -> ImpactDispositionOutcome:
    normalized_title = _required(title, "corrective feature title")
    normalized_plan = _required(plan, "corrective feature plan")
    dependencies = _accepted_dependencies(decision, root=root)
    if not dependencies:
        raise ImpactDispositionError(
            "corrective work requires at least one explicit accepted-work dependency"
        )
    body = (
        f"{normalized_plan}\n\n"
        "### Corrective-work authorization\n\n"
        f"- Epic impact decision: `{decision.id}`\n"
        f"- Originating thread: `{decision.root_comment_id}` on `{decision.source_feature_id}`\n"
        f"- Held/affected work: {', '.join(f'`{item}`' for item in decision.affected_work_ids)}\n"
        f"- Accepted-work dependencies: {', '.join(f'`{item}`' for item in dependencies)}\n"
        "- Approval: this plan requires revision-bound Epic Manager and Epic Architect "
        "sign-offs plus a new human feature approval; prior Epic approval does not apply."
    )
    feature_id = mint_feature(
        normalized_title,
        depends_on=list(dependencies),
        body_stub=body,
        epic_id=epic_id,
        root=root,
    )
    reply_id = reply_comment(
        decision.source_feature_id,
        decision.root_comment_id,
        (
            f"Corrective feature {feature_id} was created in backlog for decision "
            f"{decision.id}, depending on accepted work {', '.join(dependencies)}. "
            "It remains unapproved until its current plan receives both planning "
            "sign-offs and separate human approval. Affected work remains held."
        ),
        author=author,
        root=root,
    )
    return ImpactDispositionOutcome(
        decision_id=decision.id,
        handoff_id=decision.handoff_id,
        disposition="corrective_feature",
        source_feature_id=decision.source_feature_id,
        root_comment_id=decision.root_comment_id,
        affected_work_ids=decision.affected_work_ids,
        corrective_feature_id=feature_id,
        accepted_dependency_ids=dependencies,
        requested_human_action=None,
        originating_thread_reply_reference=reply_id,
        applied_by=author,
        applied_at=datetime.now(timezone.utc),
    )


def _apply_human_blocker(
    decision: EpicImpactDecision,
    *,
    requested_human_action: str | None,
    author: CorrectivePlanningRole,
    root: Path,
) -> ImpactDispositionOutcome:
    action = _required(requested_human_action, "requested human replacement/replanning action")
    reply_id = reply_comment(
        decision.source_feature_id,
        decision.root_comment_id,
        (
            f"Human decision required for Epic impact decision {decision.id}. {action} "
            f"Held/affected work: {', '.join(decision.affected_work_ids)}. No work was "
            "returned to backlog and no accepted-work state was reset."
        ),
        author=author,
        root=root,
    )
    return ImpactDispositionOutcome(
        decision_id=decision.id,
        handoff_id=decision.handoff_id,
        disposition="human_blocker",
        source_feature_id=decision.source_feature_id,
        root_comment_id=decision.root_comment_id,
        affected_work_ids=decision.affected_work_ids,
        corrective_feature_id=None,
        accepted_dependency_ids=(),
        requested_human_action=action,
        originating_thread_reply_reference=reply_id,
        applied_by=author,
        applied_at=datetime.now(timezone.utc),
    )


def _require_decision(decision_id: str, *, epic_id: str, root: Path) -> EpicImpactDecision:
    decision = next(
        (
            row
            for row in read_epic_impact_decisions(root=root)
            if row.id == decision_id
        ),
        None,
    )
    if decision is None:
        raise ImpactDispositionError(f"unknown Epic impact decision {decision_id}")
    board = merged_board(root)
    source = board.by_id.get(decision.source_feature_id)
    if source is None or source.tier != "feature" or source.parent != epic_id:
        raise EpicToolDenied("Epic impact decision belongs to another Epic Team")
    if decision.materiality != "material" or not decision.relayed:
        raise ImpactDispositionError("disposition requires a relayed material Epic decision")
    return decision


def _accepted_dependencies(
    decision: EpicImpactDecision, *, root: Path
) -> tuple[str, ...]:
    board = merged_board(root)
    values = list(decision.accepted_sibling_ids)
    for work_id in decision.affected_work_ids:
        meta = board.by_id.get(work_id)
        if meta is not None and meta.tier == "feature" and meta.status == "completed":
            values.append(work_id)
    dependencies = tuple(dict.fromkeys(values))
    if any(
        (meta := board.by_id.get(work_id)) is None
        or meta.tier != "feature"
        or meta.status != "completed"
        for work_id in dependencies
    ):
        raise ImpactDispositionError("accepted-work dependency evidence is stale")
    return dependencies


def _corrective_revision(outcome: ImpactDispositionOutcome, *, root: Path) -> str:
    assert outcome.corrective_feature_id is not None
    doc = read_doc(outcome.corrective_feature_id, root=root)
    plan_contract = {
        "title": doc.meta.title,
        "parent": doc.meta.parent,
        "depends_on": doc.meta.depends_on,
        "owners": doc.meta.owners,
        "skills": [str(item) for item in doc.meta.skills],
        "provider": doc.meta.provider,
        "model": doc.meta.model,
        "models": doc.meta.models,
        "reasoning": doc.meta.reasoning,
        "flex_mode": doc.meta.flex_mode,
        "body": doc.body,
    }
    return hashlib.sha256(
        json.dumps(
            plan_contract,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _outcome_view(
    outcome: ImpactDispositionOutcome, *, root: Path
) -> dict[str, object]:
    value = outcome.to_dict()
    if outcome.corrective_feature_id is not None:
        revision = _corrective_revision(outcome, root=root)
        signed = {
            row.role for row in outcome.sign_offs if row.plan_revision == revision
        }
        value.update(
            {
                "plan_revision": revision,
                "required_sign_offs": list(_REQUIRED_ROLES),
                "current_sign_offs": [role for role in _REQUIRED_ROLES if role in signed],
                "ready_for_human_approval": all(
                    role in signed for role in _REQUIRED_ROLES
                ),
                "human_approved": read_doc(
                    outcome.corrective_feature_id, root=root
                ).meta.approved_at
                is not None,
            }
        )
    return value


def _require_same_application(
    outcome: ImpactDispositionOutcome,
    *,
    title: str | None,
    plan: str | None,
    requested_human_action: str | None,
    root: Path,
) -> None:
    if outcome.disposition == "human_blocker":
        if _required(requested_human_action, "requested human replacement/replanning action") != outcome.requested_human_action:
            raise ImpactDispositionError("decision already has a different disposition outcome")
        if title is not None or plan is not None:
            raise ImpactDispositionError("human blocker does not accept a corrective plan")
        return
    if requested_human_action is not None:
        raise ImpactDispositionError("corrective feature does not accept a human blocker action")
    feature = read_doc(outcome.corrective_feature_id or "", root=root)
    if _required(title, "corrective feature title") != feature.meta.title:
        raise ImpactDispositionError("decision already has a different corrective feature")
    marker = _required(plan, "corrective feature plan")
    if marker not in feature.body:
        raise ImpactDispositionError("decision already has a different corrective plan")


def _outcome_for_decision(
    decision_id: str, *, root: Path
) -> ImpactDispositionOutcome | None:
    return next(
        (row for row in _read_ledger(root) if row.decision_id == decision_id), None
    )


def _read_ledger(root: Path) -> list[ImpactDispositionOutcome]:
    path = root / _LEDGER
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise ImpactDispositionError("Epic disposition outcome ledger is malformed") from exc
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("outcomes"), list):
        raise ImpactDispositionError("Epic disposition outcome ledger is unsupported")
    try:
        return [ImpactDispositionOutcome.from_dict(item) for item in raw["outcomes"]]
    except (TypeError, ValueError) as exc:
        raise ImpactDispositionError("Epic disposition outcome ledger has an invalid row") from exc


def _write_ledger(root: Path, rows: list[ImpactDispositionOutcome]) -> None:
    path = root / _LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"version": 1, "outcomes": [row.to_dict() for row in rows]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _role(value: str) -> CorrectivePlanningRole:
    if value not in _REQUIRED_ROLES:
        raise EpicToolDenied("corrective dispositions require an Epic planning role")
    return value  # type: ignore[return-value]


def _required(value: str | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImpactDispositionError(f"{label} is required")
    return value.strip()


def _string(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("non-empty string required")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return _string(value)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_stamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


register_epic_tool("apply_impact_disposition", apply_impact_disposition)
register_epic_tool("sign_off_corrective_plan", sign_off_corrective_plan)
