"""Durable Epic impact triage for feature-plan change requests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_root
from cascade.comments.handoffs import ChangeRequestHandoff, read_change_request_handoffs
from cascade.comments.store import reply_comment
from cascade.epic.decisions import record_decision
from cascade.epic.guard import EpicToolDenied
from cascade.epic.registry import register_epic_tool
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import locate_trunk, merged_board

Materiality = Literal["material", "non_material"]
ImpactReason = Literal[
    "feature_plan",
    "epic_constraint",
    "sibling_work",
    "accepted_work",
    "architecture",
    "sequencing",
]
ImpactDisposition = Literal[
    "open_work_amendment",
    "contract_amendment",
    "corrective_feature",
    "human_blocker",
]

_REASONS = {
    "feature_plan",
    "epic_constraint",
    "sibling_work",
    "accepted_work",
    "architecture",
    "sequencing",
}
_DISPOSITIONS = {
    "open_work_amendment",
    "contract_amendment",
    "corrective_feature",
    "human_blocker",
}
_LEDGER = Path("docs") / "_comments" / "_epic_impact_decisions.json"


class EpicImpactDecisionError(Exception):
    """An Epic impact decision is invalid or conflicts with durable evidence."""


@dataclass(frozen=True)
class EpicImpactDecision:
    """One Epic disposition and its evidence for an accountable handoff."""

    id: str
    handoff_id: str
    root_comment_id: str
    source_feature_id: str
    affected_work_ids: tuple[str, ...]
    accepted_sibling_ids: tuple[str, ...]
    accepted_baseline: dict[str, Any] | None
    materiality: Materiality
    impact_reasons: tuple[ImpactReason, ...]
    disposition: ImpactDisposition
    decision_log_reference: str
    originating_thread_reply_reference: str | None
    outcome: str
    decided_by: str
    decided_at: datetime

    @property
    def relayed(self) -> bool:
        return self.originating_thread_reply_reference is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "handoff_id": self.handoff_id,
            "root_comment_id": self.root_comment_id,
            "source_feature_id": self.source_feature_id,
            "affected_work_ids": list(self.affected_work_ids),
            "accepted_sibling_ids": list(self.accepted_sibling_ids),
            "accepted_baseline": self.accepted_baseline,
            "materiality": self.materiality,
            "impact_reasons": list(self.impact_reasons),
            "disposition": self.disposition,
            "decision_log_reference": self.decision_log_reference,
            "originating_thread_reply_reference": self.originating_thread_reply_reference,
            "outcome": self.outcome,
            "decided_by": self.decided_by,
            "decided_at": _stamp(self.decided_at),
            "relayed": self.relayed,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EpicImpactDecision":
        return cls(
            id=str(raw["id"]),
            handoff_id=str(raw["handoff_id"]),
            root_comment_id=str(raw["root_comment_id"]),
            source_feature_id=str(raw["source_feature_id"]),
            affected_work_ids=tuple(str(item) for item in raw["affected_work_ids"]),
            accepted_sibling_ids=tuple(
                str(item) for item in raw.get("accepted_sibling_ids", [])
            ),
            accepted_baseline=dict(raw["accepted_baseline"])
            if raw.get("accepted_baseline") is not None
            else None,
            materiality=str(raw["materiality"]),  # type: ignore[arg-type]
            impact_reasons=tuple(
                str(item) for item in raw["impact_reasons"]
            ),  # type: ignore[arg-type]
            disposition=str(raw["disposition"]),  # type: ignore[arg-type]
            decision_log_reference=str(raw["decision_log_reference"]),
            originating_thread_reply_reference=str(
                raw["originating_thread_reply_reference"]
            )
            if raw.get("originating_thread_reply_reference")
            else None,
            outcome=str(raw["outcome"]),
            decided_by=str(raw["decided_by"]),
            decided_at=_parse_stamp(raw["decided_at"]),
        )


def record_impact_decision(
    handoff_id: str,
    materiality: str,
    impact_reasons: list[str],
    disposition: str,
    outcome: str,
    *,
    epic_id: str,
    root: Path,
    affected_work_ids: list[str] | None = None,
    author: str = "epic_manager",
) -> dict[str, Any]:
    """Record an Epic disposition, then relay it in the originating thread."""

    repo = locate_trunk(resolve_root(root))
    with process_lock:
        if author not in ("epic_manager", "epic_architect"):
            raise EpicToolDenied("impact decisions require an Epic planning role")
        handoff = _require_handoff(handoff_id, epic_id=epic_id, root=repo)
        rows = _read_ledger(repo)
        existing = next((row for row in rows if row.handoff_id == handoff_id), None)
        if existing is not None:
            _require_same_request(
                existing,
                materiality=materiality,
                impact_reasons=impact_reasons,
                disposition=disposition,
                outcome=outcome,
                affected_work_ids=affected_work_ids,
            )
            return _relay_if_needed(existing, rows=rows, root=repo).to_dict()

        classification = _classification(materiality, impact_reasons)
        if disposition not in _DISPOSITIONS:
            raise EpicImpactDecisionError(f"unknown impact disposition {disposition!r}")
        explanation = outcome.strip()
        if not explanation:
            raise EpicImpactDecisionError("decision outcome is required")

        board = merged_board(repo)
        affected = _affected_scope(handoff, affected_work_ids, board=board, epic_id=epic_id)
        accepted_siblings = tuple(
            sorted(
                meta.id
                for meta in board.by_id.values()
                if meta.tier == "feature"
                and meta.parent == epic_id
                and meta.id != handoff.source_feature_id
                and meta.status == "completed"
            )
        )
        reasons = list(classification)
        if materiality == "material" and accepted_siblings and "accepted_work" not in reasons:
            reasons.append("accepted_work")
        baseline = _accepted_baseline(epic_id, repo)
        decision_id = _decision_id(handoff_id)
        decision_log_reference = record_decision(
            "Feature change impact triage",
            _decision_log_choice(
                decision_id,
                handoff,
                affected,
                accepted_siblings,
                baseline,
                materiality,
                reasons,
                disposition,
            ),
            explanation,
            f"Originating thread {handoff.root_comment_id}; handoff {handoff.id}.",
            epic_id=epic_id,
            root=repo,
            author=author,
        )
        decision = EpicImpactDecision(
            id=decision_id,
            handoff_id=handoff.id,
            root_comment_id=handoff.root_comment_id,
            source_feature_id=handoff.source_feature_id,
            affected_work_ids=affected,
            accepted_sibling_ids=accepted_siblings,
            accepted_baseline=baseline,
            materiality=materiality,  # type: ignore[arg-type]
            impact_reasons=tuple(reasons),  # type: ignore[arg-type]
            disposition=disposition,  # type: ignore[arg-type]
            decision_log_reference=decision_log_reference,
            originating_thread_reply_reference=None,
            outcome=explanation,
            decided_by=author,
            decided_at=datetime.now(timezone.utc),
        )
        rows.append(decision)
        _write_ledger(repo, rows)
        return _relay_if_needed(decision, rows=rows, root=repo).to_dict()


def read_epic_impact_decisions(
    *, root: Path, source_feature_id: str | None = None
) -> list[EpicImpactDecision]:
    repo = locate_trunk(resolve_root(root))
    with process_lock:
        rows = _read_ledger(repo)
    if source_feature_id is not None:
        rows = [row for row in rows if row.source_feature_id == source_feature_id]
    return rows


def _require_handoff(
    handoff_id: str, *, epic_id: str, root: Path
) -> ChangeRequestHandoff:
    handoff = next(
        (row for row in read_change_request_handoffs(root=root) if row.id == handoff_id),
        None,
    )
    if handoff is None:
        raise EpicImpactDecisionError(f"unknown change-request handoff {handoff_id}")
    if handoff.status != "delivered" or handoff.receiving_team != "epic":
        raise EpicImpactDecisionError("impact triage requires a delivered Epic handoff")
    if handoff.receiving_owner != epic_id:
        raise EpicToolDenied("change-request handoff belongs to another Epic Team")
    board = merged_board(root)
    feature = board.by_id.get(handoff.source_feature_id)
    if feature is None or feature.tier != "feature" or feature.parent != epic_id:
        raise EpicToolDenied("change-request source is not a child of this epic")
    # Active features first deliver to their Feature Team.  They reach the Epic
    # only through the explicit, durable impact-triage escalation.
    if feature.path.parent.name == "2_active" and handoff.purpose != "epic_impact_triage":
        raise EpicImpactDecisionError("active feature requires explicit Epic escalation")
    return handoff


def _classification(materiality: str, reasons: list[str]) -> tuple[str, ...]:
    if materiality not in ("material", "non_material"):
        raise EpicImpactDecisionError("materiality must be material or non_material")
    if not isinstance(reasons, list):
        raise EpicImpactDecisionError("impact_reasons must be a list")
    normalized = tuple(dict.fromkeys(str(reason).strip() for reason in reasons))
    if any(not reason or reason not in _REASONS for reason in normalized):
        raise EpicImpactDecisionError("impact_reasons contains an unknown classification")
    if materiality == "material" and not normalized:
        raise EpicImpactDecisionError("material requests require an impact reason")
    if materiality == "non_material" and any(
        reason != "feature_plan" for reason in normalized
    ):
        raise EpicImpactDecisionError("cross-work impact reasons are material")
    return normalized


def _affected_scope(
    handoff: ChangeRequestHandoff,
    requested: list[str] | None,
    *,
    board: Any,
    epic_id: str,
) -> tuple[str, ...]:
    values = list(requested) if requested is not None else list(handoff.affected_work_ids)
    if handoff.source_feature_id not in values:
        values.insert(0, handoff.source_feature_id)
    affected = tuple(dict.fromkeys(str(item) for item in values))
    for work_id in affected:
        meta = board.by_id.get(work_id)
        if meta is None:
            raise EpicImpactDecisionError(f"unknown affected work id {work_id}")
        if not _belongs_to_epic(meta, epic_id, board):
            raise EpicToolDenied(f"affected work {work_id} belongs outside {epic_id}")
    return affected


def _belongs_to_epic(meta: Any, epic_id: str, board: Any) -> bool:
    current = meta
    visited: set[str] = set()
    while current.id not in visited:
        if current.id == epic_id:
            return True
        visited.add(current.id)
        if current.parent is None:
            return False
        current = board.by_id.get(current.parent)
        if current is None:
            return False
    return False


def _accepted_baseline(epic_id: str, root: Path) -> dict[str, Any] | None:
    path = root / "architecture" / "review-units.json"
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        entries = state.get("lineages", {}).get(f"epic:{epic_id}", [])
        latest = entries[-1] if entries else None
    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise EpicImpactDecisionError("accepted architecture lineage is unreadable") from exc
    if latest is None:
        return None
    if not isinstance(latest, dict):
        raise EpicImpactDecisionError("accepted architecture lineage is malformed")
    required = (
        "generation",
        "accepted_review_unit_id",
        "accepted_tuple_digest",
        "accepted_code_head",
        "accepted_documentation_head",
    )
    if any(field not in latest for field in required):
        raise EpicImpactDecisionError("accepted architecture lineage is malformed")
    pointer_digest = hashlib.sha256(
        json.dumps(latest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return {
        "lineage": f"epic:{epic_id}",
        "generation": latest["generation"],
        "accepted_review_unit_id": latest["accepted_review_unit_id"],
        "accepted_tuple_digest": latest["accepted_tuple_digest"],
        "accepted_code_head": latest["accepted_code_head"],
        "accepted_documentation_head": latest["accepted_documentation_head"],
        "pointer_id": f"accepted-lineage-{pointer_digest}",
    }


def _decision_log_choice(
    decision_id: str,
    handoff: ChangeRequestHandoff,
    affected: tuple[str, ...],
    siblings: tuple[str, ...],
    baseline: dict[str, Any] | None,
    materiality: str,
    reasons: list[str],
    disposition: str,
) -> str:
    generation = baseline["generation"] if baseline else "none"
    return (
        f"{decision_id}: {materiality} request {handoff.id}; disposition {disposition}; "
        f"affected {', '.join(affected)}; accepted siblings "
        f"{', '.join(siblings) if siblings else 'none'}; baseline generation {generation}; "
        f"impact {', '.join(reasons) if reasons else 'none'}."
    )


def _relay_if_needed(
    decision: EpicImpactDecision,
    *,
    rows: list[EpicImpactDecision],
    root: Path,
) -> EpicImpactDecision:
    if decision.originating_thread_reply_reference is not None:
        return decision
    body = (
        f"Epic impact decision {decision.id} ({decision.disposition}): "
        f"{decision.outcome}"
    )
    reply_id = reply_comment(
        decision.source_feature_id,
        decision.root_comment_id,
        body,
        author=decision.decided_by,
        root=root,
    )
    relayed = replace(decision, originating_thread_reply_reference=reply_id)
    updated = [relayed if row.id == decision.id else row for row in rows]
    _write_ledger(root, updated)
    return relayed


def _require_same_request(
    decision: EpicImpactDecision,
    *,
    materiality: str,
    impact_reasons: list[str],
    disposition: str,
    outcome: str,
    affected_work_ids: list[str] | None,
) -> None:
    reasons = list(_classification(materiality, impact_reasons))
    # accepted_work is system-added when completed sibling evidence exists.
    if "accepted_work" in decision.impact_reasons and "accepted_work" not in reasons:
        reasons.append("accepted_work")
    requested_scope = None
    if affected_work_ids is not None:
        values = list(affected_work_ids)
        if decision.source_feature_id not in values:
            values.insert(0, decision.source_feature_id)
        requested_scope = tuple(dict.fromkeys(values))
    same = (
        decision.materiality == materiality
        and decision.impact_reasons == tuple(reasons)
        and decision.disposition == disposition
        and decision.outcome == outcome.strip()
        and (requested_scope is None or decision.affected_work_ids == requested_scope)
    )
    if not same:
        raise EpicImpactDecisionError("handoff already has a different Epic decision")


def _decision_id(handoff_id: str) -> str:
    return "eid_" + hashlib.sha256(handoff_id.encode("utf-8")).hexdigest()[:20]


def _read_ledger(root: Path) -> list[EpicImpactDecision]:
    path = root / _LEDGER
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise EpicImpactDecisionError("Epic impact decision ledger is malformed") from exc
    if not isinstance(raw, list):
        raise EpicImpactDecisionError("Epic impact decision ledger must be a list")
    try:
        rows = [EpicImpactDecision.from_dict(item) for item in raw if isinstance(item, dict)]
    except (KeyError, TypeError, ValueError) as exc:
        raise EpicImpactDecisionError("Epic impact decision ledger has an invalid row") from exc
    if len(rows) != len(raw) or any(
        row.materiality not in ("material", "non_material")
        or row.disposition not in _DISPOSITIONS
        or any(reason not in _REASONS for reason in row.impact_reasons)
        for row in rows
    ):
        raise EpicImpactDecisionError("Epic impact decision ledger has an invalid row")
    return rows


def _write_ledger(root: Path, rows: list[EpicImpactDecision]) -> None:
    path = root / _LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps([row.to_dict() for row in rows], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_stamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


register_epic_tool("record_impact_decision", record_impact_decision)
