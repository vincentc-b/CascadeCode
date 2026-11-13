"""Owner-scoped architecture authoring and upward amendment routing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.board.types import WorkDoc
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event
from cascade.workspace.architecture_review import (
    ArchitectureProposalError,
    ArchitectureProposalState,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    _validate_proposed_model,
    _validate_store_inputs,
    stage_architecture_proposal,
)
from cascade.workspace.c4_diff import C4SemanticModelArtifact
from cascade.workspace.c4_render import C4ArtifactRenderer, C4RenderSettings
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.types import ProjectContext

AuthoringDisposition = Literal["owner_staged_review", "routed_owner_amendment"]
_LEDGER = Path("architecture") / "owner-amendments.json"


@dataclass(frozen=True)
class ArchitectureAuthoringIntent:
    """An exact proposal submitted by a work team for its artifact owner."""

    originating_work_id: str
    actor: str
    proposal: ArchitectureReviewUnit
    expected_generation: int | None
    originating_comment_id: str | None = None


@dataclass(frozen=True)
class ArchitectureOwnerAmendment:
    """A validated proposal routed upward without changing accepted artifacts."""

    amendment_id: str
    originating_work_id: str
    originating_comment_id: str | None
    owning_work_id: str
    owning_actor: str
    affected_work_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    view_ids: tuple[str, ...]
    base_generation: int | None
    proposed_review_unit_id: str
    proposed_tuple_digest: str
    proposal: ArchitectureReviewUnit
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "amendment_id": self.amendment_id,
            "originating_work_id": self.originating_work_id,
            "originating_comment_id": self.originating_comment_id,
            "owning_work_id": self.owning_work_id,
            "owning_actor": self.owning_actor,
            "affected_work_ids": list(self.affected_work_ids),
            "requirement_ids": list(self.requirement_ids),
            "decision_ids": list(self.decision_ids),
            "view_ids": list(self.view_ids),
            "base_generation": self.base_generation,
            "proposed_review_unit_id": self.proposed_review_unit_id,
            "proposed_tuple_digest": self.proposed_tuple_digest,
            "proposal": self.proposal.to_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ArchitectureOwnerAmendment":
        if not isinstance(value, dict):
            raise ArchitectureProposalError(
                "review_required", "architecture amendment ledger has an invalid row"
            )
        try:
            return cls(
                amendment_id=str(value["amendment_id"]),
                originating_work_id=str(value["originating_work_id"]),
                originating_comment_id=(
                    str(value["originating_comment_id"])
                    if value.get("originating_comment_id") is not None
                    else None
                ),
                owning_work_id=str(value["owning_work_id"]),
                owning_actor=str(value["owning_actor"]),
                affected_work_ids=tuple(str(item) for item in value["affected_work_ids"]),
                requirement_ids=tuple(str(item) for item in value["requirement_ids"]),
                decision_ids=tuple(str(item) for item in value["decision_ids"]),
                view_ids=tuple(str(item) for item in value["view_ids"]),
                base_generation=value["base_generation"],
                proposed_review_unit_id=str(value["proposed_review_unit_id"]),
                proposed_tuple_digest=str(value["proposed_tuple_digest"]),
                proposal=ArchitectureReviewUnit.from_dict(value["proposal"]),
                created_at=str(value["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ArchitectureProposalError(
                "review_required", "architecture amendment ledger has an invalid row"
            ) from exc


@dataclass(frozen=True)
class ArchitectureAuthoringResult:
    disposition: AuthoringDisposition
    staged: ArchitectureProposalState | None = None
    amendment: ArchitectureOwnerAmendment | None = None

    def __post_init__(self) -> None:
        if self.disposition == "owner_staged_review":
            if self.staged is None or self.amendment is not None:
                raise ValueError("owned authoring requires only a staged proposal")
        elif self.disposition == "routed_owner_amendment":
            if self.amendment is None or self.staged is not None:
                raise ValueError("routed authoring requires only an owner amendment")
        else:
            raise ValueError("unknown architecture authoring disposition")


def stage_owned_architecture_change(
    project: ProjectContext,
    intent: ArchitectureAuthoringIntent,
    *,
    store: ArchitectureReviewStore | None = None,
    renderer: C4ArtifactRenderer | None = None,
    render_settings: C4RenderSettings | None = None,
    baseline_artifact: C4SemanticModelArtifact | None = None,
    lineage_revision: str | None = None,
    plan_work_id: str | None = None,
) -> ArchitectureAuthoringResult:
    """Stage an owned proposal or route an ancestor-owned proposal to its owner.

    Routing validates the same pinned inputs and baseline as staging, but does
    not insert a review unit or alter the accepted lineage.  The receiving owner
    must submit the exact proposal through this function before it is reviewable.
    """

    proposal = intent.proposal
    _require_nonblank(intent.originating_work_id, "originating work ID")
    _require_nonblank(intent.actor, "authoring actor")
    review_store = store or ArchitectureReviewStore(project)
    _validate_intent(
        project, intent, review_store, renderer=renderer,
        render_settings=render_settings, baseline_artifact=baseline_artifact,
        lineage_revision=lineage_revision,
        plan_work_id=plan_work_id,
    )

    if intent.originating_work_id == proposal.owner_work_id:
        staged = stage_architecture_proposal(
            project,
            owner=intent.actor,
            work_id=intent.originating_work_id,
            proposal=proposal,
            expected_generation=intent.expected_generation,
            store=review_store,
            renderer=renderer,
            render_settings=render_settings,
            baseline_artifact=baseline_artifact,
            lineage_revision=lineage_revision,
            plan_work_id=plan_work_id,
        )
        return ArchitectureAuthoringResult("owner_staged_review", staged=staged)

    amendment = _route_amendment(project, intent)
    return ArchitectureAuthoringResult(
        "routed_owner_amendment", amendment=amendment
    )


def read_owner_amendments(
    project: ProjectContext, *, owning_work_id: str
) -> tuple[ArchitectureOwnerAmendment, ...]:
    """Read only amendment requests addressed to one architecture owner."""

    _read_work(project, owning_work_id)
    return tuple(
        row for row in _read_ledger(project) if row.owning_work_id == owning_work_id
    )


def _validate_intent(
    project: ProjectContext,
    intent: ArchitectureAuthoringIntent,
    store: ArchitectureReviewStore,
    *,
    renderer: C4ArtifactRenderer | None,
    render_settings: C4RenderSettings | None,
    baseline_artifact: C4SemanticModelArtifact | None,
    lineage_revision: str | None,
    plan_work_id: str | None,
) -> None:
    proposal = intent.proposal
    origin = _read_work(project, intent.originating_work_id)
    owner = _read_work(project, proposal.owner_work_id)
    if origin.meta.id != owner.meta.id and not _is_pinned_ancestor(project, origin, owner.meta.id):
        raise ArchitectureProposalError(
            "owner_denied", "architecture proposal owner is not in the caller's ancestor scope"
        )

    references = [proposal.design.reference]
    if proposal.proposed_model is not None:
        references.extend(
            item.reference
            for item in (proposal.proposed_model.contract, *proposal.proposed_model.sources)
        )
    if any(reference.owning_work != owner.meta.id for reference in references):
        raise ArchitectureProposalError(
            "owner_denied", "design and model artifacts must share the proposal owner"
        )
    if not proposal.requirement_citations or not proposal.decision_citations:
        raise ArchitectureProposalError(
            "review_required",
            "architecture proposals require requirement and decision citations",
        )
    if proposal.architecture_impact == "diagram_change" and not proposal.view_citations:
        raise ArchitectureProposalError(
            "review_required", "a diagram change requires affected view citations"
        )
    if proposal.status not in {"draft", "staged"}:
        raise ArchitectureProposalError(
            "review_required", "only a draft proposal can be authored"
        )
    if origin.meta.id == owner.meta.id and proposal.authorized_owner != intent.actor:
        raise ArchitectureProposalError(
            "owner_denied", "architecture proposal is outside the caller's owner scope"
        )

    current = store.resolve_current(
        proposal.integration_lineage, lineage_revision=lineage_revision
    )
    generation = current.generation if current else None
    if generation != intent.expected_generation:
        raise ArchitectureProposalError(
            "stale_baseline", "accepted architecture baseline generation changed"
        )
    if store.baseline_status(proposal, lineage_revision=lineage_revision).stale:
        raise ArchitectureProposalError(
            "stale_baseline", "proposal is not based on the current accepted architecture"
        )
    _validate_store_inputs(
        store,
        proposal,
        lineage_revision=lineage_revision,
        plan_work_id=plan_work_id,
    )
    _validate_proposed_model(
        project,
        proposal,
        renderer=renderer,
        settings=render_settings,
        baseline_artifact=baseline_artifact,
    )


def _route_amendment(
    project: ProjectContext, intent: ArchitectureAuthoringIntent
) -> ArchitectureOwnerAmendment:
    proposal = intent.proposal
    identity = {
        "originating_work_id": intent.originating_work_id,
        "originating_comment_id": intent.originating_comment_id,
        "owning_work_id": proposal.owner_work_id,
        "proposed_tuple_digest": proposal.reviewed_tuple_digest,
        "base_generation": intent.expected_generation,
    }
    amendment_id = "architecture-amendment-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    proposed = ArchitectureOwnerAmendment(
        amendment_id=amendment_id,
        originating_work_id=intent.originating_work_id,
        originating_comment_id=intent.originating_comment_id,
        owning_work_id=proposal.owner_work_id,
        owning_actor=proposal.authorized_owner,
        affected_work_ids=proposal.affected_work_ids,
        requirement_ids=proposal.requirement_citations,
        decision_ids=proposal.decision_citations,
        view_ids=proposal.view_citations,
        base_generation=intent.expected_generation,
        proposed_review_unit_id=proposal.review_unit_id,
        proposed_tuple_digest=proposal.reviewed_tuple_digest,
        proposal=proposal,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    with process_lock:
        rows = list(_read_ledger(project))
        existing = next(
            (row for row in rows if row.amendment_id == amendment_id), None
        )
        if existing is not None:
            proposed = existing
        else:
            rows.append(proposed)
            _write_ledger(project, rows)
        _emit_owner_event(project, proposed)
    return proposed


def _emit_owner_event(
    project: ProjectContext, amendment: ArchitectureOwnerAmendment
) -> None:
    events, _ = read_events(
        amendment.owning_work_id, 0, root=project.tracking.root
    )
    if any(
        event.type == "ArchitectureAmendmentRequested"
        and event.payload.get("amendment_id") == amendment.amendment_id
        for event in events
    ):
        return
    append_event(
        amendment.owning_work_id,
        Event(
            type="ArchitectureAmendmentRequested",
            ts=datetime.now(timezone.utc),
            payload={
                "amendment_id": amendment.amendment_id,
                "originating_work_id": amendment.originating_work_id,
                "originating_comment_id": amendment.originating_comment_id,
                "owning_work_id": amendment.owning_work_id,
                "affected_work_ids": list(amendment.affected_work_ids),
                "requirement_ids": list(amendment.requirement_ids),
                "decision_ids": list(amendment.decision_ids),
                "view_ids": list(amendment.view_ids),
                "proposed_review_unit_id": amendment.proposed_review_unit_id,
                "proposed_tuple_digest": amendment.proposed_tuple_digest,
                "base_generation": amendment.base_generation,
            },
            dest=amendment.owning_work_id,
        ),
        root=project.tracking.root,
    )


def _is_pinned_ancestor(
    project: ProjectContext, origin: WorkDoc, owner_id: str
) -> bool:
    current = origin
    while current.meta.parent is not None:
        if current.meta.parent == owner_id:
            return True
        if current.meta.parent_rev is None:
            return False
        try:
            current = read_doc(
                current.meta.parent,
                rev=current.meta.parent_rev,
                root=project.tracking.root,
            )
        except NotFound:
            return False
    return False


def _read_work(project: ProjectContext, work_id: str) -> WorkDoc:
    try:
        return read_doc_resolved(work_id, root=project.tracking.root)
    except NotFound:
        raise ArchitectureProposalError(
            "owner_denied", f"unknown architecture work owner {work_id}"
        ) from None


def _read_ledger(project: ProjectContext) -> tuple[ArchitectureOwnerAmendment, ...]:
    path = project.target.root / _LEDGER
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchitectureProposalError(
            "review_required", "architecture amendment ledger is unreadable"
        ) from exc
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("amendments"), list):
        raise ArchitectureProposalError(
            "review_required", "architecture amendment ledger is unsupported"
        )
    return tuple(ArchitectureOwnerAmendment.from_dict(row) for row in raw["amendments"])


def _write_ledger(
    project: ProjectContext, rows: list[ArchitectureOwnerAmendment]
) -> None:
    path = project.target.root / _LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"version": 1, "amendments": [row.to_dict() for row in rows]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _require_nonblank(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ArchitectureProposalError("owner_denied", f"{label} is required")


__all__ = [
    "ArchitectureAuthoringIntent",
    "ArchitectureAuthoringResult",
    "ArchitectureOwnerAmendment",
    "read_owner_amendments",
    "stage_owned_architecture_change",
]
