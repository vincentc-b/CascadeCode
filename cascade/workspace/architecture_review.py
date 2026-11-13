"""Durable, revision-bound architecture review units and lineage baselines."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Mapping, Sequence

if TYPE_CHECKING:
    from cascade.workspace.blocking_scope import BlockingScope

from cascade.workspace.architecture import ArchitectureArtifactRef
from cascade.workspace.c4_closure import C4SourceClosure, materialize_c4_source_closure
from cascade.workspace.c4_diff import (
    C4ContainmentChange,
    C4IdentityChange,
    C4SemanticDiff,
    C4SemanticModelArtifact,
    C4ViewDiff,
    compute_c4_semantic_diff,
)
from cascade.workspace.c4_render import (
    C4ArtifactRenderer,
    C4RenderArtifact,
    C4RenderSettings,
)
from cascade.workspace.c4_scheduler import render_identity
from cascade.workspace.c4_source import C4SourceError
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.integration_worktree import (
    integration_branch,
    integration_worktree_path,
    load_registry_readonly,
    locate_trunk,
)
from cascade.workspace.types import ProjectContext, RepositoryContext

_SCHEMA_VERSION = 1
_REVISION = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_REVIEW_GATE_NAME = "revision_bound_architecture"
RepositoryRole = Literal["target", "tracking"]
ReviewStatus = Literal["draft", "staged", "reviewed", "approved", "stale", "rejected"]
ReviewDecision = Literal["reviewed", "rejected"]
ReviewGateBoundary = Literal["approval", "dispatch", "integration", "merge", "closeout"]
PromotionSideState = Literal["pending", "landed"]
PromotionOutcome = Literal["reserved", "acceptance_pending", "accepted", "conflict"]
_REVIEW_GATE_BOUNDARIES = {"approval", "dispatch", "integration", "merge", "closeout"}


class ArchitectureProposalError(WorkspaceError):
    """A stable proposal outcome suitable for lifecycle/API callers."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ReviewApprovalContext:
    """The exact architecture evidence displayed before human approval."""

    owner_work_id: str
    target_repository_key: str
    plan_revision: str
    review_unit_id: str
    reviewed_tuple_digest: str
    accepted_baseline_generation: int | None

    def __post_init__(self) -> None:
        _nonblank(self.owner_work_id, "review approval owner")
        _nonblank(self.target_repository_key, "review approval repository")
        _revision(self.plan_revision, "review approval plan")
        _nonblank(self.review_unit_id, "review approval unit")
        _digest(self.reviewed_tuple_digest, "review approval tuple")
        _generation(
            self.accepted_baseline_generation,
            "review approval baseline generation",
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> "ReviewApprovalContext":
        row = _mapping(value, {
            "owner_work_id", "target_repository_key", "plan_revision",
            "review_unit_id", "reviewed_tuple_digest",
            "accepted_baseline_generation",
        })
        strings = (
            "owner_work_id", "target_repository_key", "plan_revision",
            "review_unit_id", "reviewed_tuple_digest",
        )
        if not all(isinstance(row[field], str) for field in strings):
            raise WorkspaceError("invalid review approval context")
        return cls(
            row["owner_work_id"], row["target_repository_key"],
            row["plan_revision"], row["review_unit_id"],
            row["reviewed_tuple_digest"], row["accepted_baseline_generation"],
        )


@dataclass(frozen=True)
class PinnedDocumentRef:
    repository_key: str
    repository_role: RepositoryRole
    path: Path
    revision: str
    content_digest: str

    def __post_init__(self) -> None:
        _nonblank(self.repository_key, "pinned document repository key")
        _role(self.repository_role)
        _relative_path(self.path, "pinned document")
        _revision(self.revision, "pinned document")
        _digest(self.content_digest, "pinned document content")

    def to_dict(self) -> dict[str, str]:
        return {"repository_key": self.repository_key, "repository_role": self.repository_role,
                "path": self.path.as_posix(), "revision": self.revision,
                "content_digest": self.content_digest}

    @classmethod
    def from_dict(cls, value: object) -> "PinnedDocumentRef":
        row = _mapping(value, {"repository_key", "repository_role", "path", "revision", "content_digest"})
        if not all(isinstance(item, str) for item in row.values()):
            raise WorkspaceError("invalid pinned document reference")
        _role(row["repository_role"])
        return cls(row["repository_key"], row["repository_role"], Path(row["path"]),
                   row["revision"], row["content_digest"])


@dataclass(frozen=True)
class PinnedArchitectureArtifact:
    reference: ArchitectureArtifactRef
    content_digest: str

    def __post_init__(self) -> None:
        _digest(self.content_digest, "architecture artifact content")

    def to_dict(self) -> dict[str, object]:
        return {"reference": self.reference.to_dict(), "content_digest": self.content_digest}

    @classmethod
    def from_dict(cls, value: object) -> "PinnedArchitectureArtifact":
        row = _mapping(value, {"reference", "content_digest"})
        if not isinstance(row["content_digest"], str):
            raise WorkspaceError("invalid pinned architecture artifact")
        return cls(ArchitectureArtifactRef.from_dict(row["reference"]), row["content_digest"])


@dataclass(frozen=True)
class ArchitectureModelBinding:
    """Exact model closure and renderer output bound by review."""

    contract: PinnedArchitectureArtifact
    sources: tuple[PinnedArchitectureArtifact, ...]
    source_closure_digest: str
    renderer_image_digest: str
    renderer_settings: tuple[tuple[str, str | int | float | bool], ...]
    semantic_artifact_digest: str
    render_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.sources:
            raise WorkspaceError("a diagram change requires a nonempty model closure")
        _digest(self.source_closure_digest, "model source closure")
        _digest(self.renderer_image_digest, "renderer image")
        _digest(self.semantic_artifact_digest, "semantic model artifact")
        if self.render_identity is not None:
            _digest(self.render_identity, "render identity")
        keys = [key for key, _ in self.renderer_settings]
        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise WorkspaceError("renderer setting names must be non-blank")
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise WorkspaceError("renderer settings must be unique and sorted")
        if any(
            not isinstance(value, (str, int, float, bool))
            for _, value in self.renderer_settings
        ):
            raise WorkspaceError("renderer settings must be immutable scalar values")
        try:
            json.dumps(dict(self.renderer_settings), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise WorkspaceError("renderer settings must be JSON values") from exc
        references = (self.contract.reference, *(item.reference for item in self.sources))
        identity = {(item.target_repository_key, item.destination_repository_key,
                     item.destination_repository_role, item.revision, item.code_directory,
                     item.design_owner_directory) for item in references}
        if len(identity) != 1:
            raise WorkspaceError("model closure references must share one pinned identity")
        paths = [item.repository_path for item in references]
        if len(paths) != len(set(paths)):
            raise WorkspaceError("model closure contains duplicate artifact paths")

    def to_dict(self) -> dict[str, object]:
        value = {"contract": self.contract.to_dict(),
                "sources": [item.to_dict() for item in self.sources],
                "source_closure_digest": self.source_closure_digest,
                "renderer_image_digest": self.renderer_image_digest,
                "renderer_settings": dict(self.renderer_settings),
                "semantic_artifact_digest": self.semantic_artifact_digest}
        if self.render_identity is not None:
            value["render_identity"] = self.render_identity
        return value

    @classmethod
    def from_dict(cls, value: object) -> "ArchitectureModelBinding":
        fields = {"contract", "sources", "source_closure_digest",
                  "renderer_image_digest", "renderer_settings",
                  "semantic_artifact_digest"}
        if not isinstance(value, dict) or frozenset(value) not in {
            frozenset(fields), frozenset({*fields, "render_identity"})
        }:
            raise WorkspaceError("invalid architecture review persistence payload")
        row = value
        if not isinstance(row["sources"], list) or not isinstance(row["renderer_settings"], dict):
            raise WorkspaceError("invalid architecture model binding")
        if not all(isinstance(row[field], str) for field in
                   ("source_closure_digest", "renderer_image_digest", "semantic_artifact_digest")):
            raise WorkspaceError("invalid architecture model binding")
        return cls(PinnedArchitectureArtifact.from_dict(row["contract"]),
                   tuple(PinnedArchitectureArtifact.from_dict(item) for item in row["sources"]),
                   row["source_closure_digest"], row["renderer_image_digest"],
                   tuple(sorted(row["renderer_settings"].items())), row["semantic_artifact_digest"],
                   row.get("render_identity"))


@dataclass(frozen=True)
class ArchitectureBaseline:
    kind: Literal["empty_baseline", "model"]
    model: ArchitectureModelBinding | None = None
    accepted_review_unit_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "empty_baseline":
            if self.model is not None or self.accepted_review_unit_id is not None:
                raise WorkspaceError("an empty baseline cannot contain model state")
        elif self.kind == "model":
            if self.model is None:
                raise WorkspaceError("a model baseline requires a pinned model")
            _nonblank(self.accepted_review_unit_id, "accepted review unit ID")
        else:
            raise WorkspaceError("invalid architecture baseline kind")

    @classmethod
    def empty(cls) -> "ArchitectureBaseline":
        return cls("empty_baseline")

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "model": self.model.to_dict() if self.model else None,
                "accepted_review_unit_id": self.accepted_review_unit_id}

    @classmethod
    def from_dict(cls, value: object) -> "ArchitectureBaseline":
        row = _mapping(value, {"kind", "model", "accepted_review_unit_id"})
        if row["kind"] not in {"empty_baseline", "model"}:
            raise WorkspaceError("invalid architecture baseline kind")
        if row["accepted_review_unit_id"] is not None and not isinstance(row["accepted_review_unit_id"], str):
            raise WorkspaceError("invalid architecture baseline")
        return cls(row["kind"], ArchitectureModelBinding.from_dict(row["model"])
                   if row["model"] is not None else None, row["accepted_review_unit_id"])


@dataclass(frozen=True)
class ProposedAncestorContext:
    review_unit_id: str
    baseline_pointer_id: str | None
    baseline_generation: int | None

    def __post_init__(self) -> None:
        _nonblank(self.review_unit_id, "ancestor review unit ID")
        if self.baseline_pointer_id is not None:
            _nonblank(self.baseline_pointer_id, "ancestor baseline pointer ID")
        _generation(self.baseline_generation, "ancestor baseline generation")

    def to_dict(self) -> dict[str, object]:
        return {"review_unit_id": self.review_unit_id,
                "baseline_pointer_id": self.baseline_pointer_id,
                "baseline_generation": self.baseline_generation}

    @classmethod
    def from_dict(cls, value: object) -> "ProposedAncestorContext":
        row = _mapping(value, {"review_unit_id", "baseline_pointer_id", "baseline_generation"})
        if not isinstance(row["review_unit_id"], str):
            raise WorkspaceError("invalid proposed ancestor context")
        return cls(row["review_unit_id"], row["baseline_pointer_id"], row["baseline_generation"])


@dataclass(frozen=True)
class ArchitectureReviewUnit:
    """ReviewUnit v1, excluding the later-bound implementation commit."""

    owner_work_id: str
    authorized_owner: str
    target_repository_key: str
    code_directory: Path
    design_owner_directory: Path
    code_repository_key: str
    integration_lineage: str
    documentation_repository_key: str
    documentation_repository_role: RepositoryRole
    documentation_destination_path: Path
    proposed_ancestor_context: ProposedAncestorContext | None
    accepted_baseline: ArchitectureBaseline
    baseline_pointer_id: str | None
    baseline_generation: int | None
    rollout_version: int
    status: ReviewStatus
    plan: PinnedDocumentRef
    design: PinnedArchitectureArtifact
    proposed_model: ArchitectureModelBinding | None
    requirement_citations: tuple[str, ...]
    decision_citations: tuple[str, ...]
    view_citations: tuple[str, ...]
    affected_work_ids: tuple[str, ...]
    architecture_impact: Literal["diagram_change", "no_diagram_change"]
    impact_reason: str

    def __post_init__(self) -> None:
        for value, field in ((self.owner_work_id, "owner work ID"),
                             (self.authorized_owner, "authorized owner"),
                             (self.target_repository_key, "target repository key"),
                             (self.code_repository_key, "code repository key"),
                             (self.integration_lineage, "integration lineage"),
                             (self.documentation_repository_key, "documentation repository key"),
                             (self.impact_reason, "architecture impact reason")):
            _nonblank(value, field)
        _relative_path(self.code_directory, "code directory", allow_root=True)
        _relative_path(self.design_owner_directory, "design owner directory", allow_root=True)
        _relative_path(
            self.documentation_destination_path,
            "documentation destination",
            allow_root=True,
        )
        _role(self.documentation_repository_role)
        if (self.baseline_pointer_id is None) != (self.baseline_generation is None):
            raise WorkspaceError("baseline pointer ID and generation must be recorded together")
        if self.baseline_pointer_id is not None:
            _nonblank(self.baseline_pointer_id, "baseline pointer ID")
        _generation(self.baseline_generation, "baseline generation")
        if not isinstance(self.rollout_version, int) or isinstance(self.rollout_version, bool) or self.rollout_version < 1:
            raise WorkspaceError("rollout version must be a positive integer")
        if self.status not in {"draft", "staged", "reviewed", "approved", "stale", "rejected"}:
            raise WorkspaceError("invalid architecture review status")
        for values, field in ((self.requirement_citations, "requirement citations"),
                              (self.decision_citations, "decision citations"),
                              (self.view_citations, "view citations"),
                              (self.affected_work_ids, "affected work IDs")):
            _unique_nonblank(values, field)
        if not self.affected_work_ids:
            raise WorkspaceError("an architecture review unit requires affected work")
        if self.architecture_impact == "diagram_change" and self.proposed_model is None:
            raise ArchitectureProposalError(
                "model_required", "a diagram change requires a pinned model closure"
            )
        if self.architecture_impact == "no_diagram_change" and self.proposed_model is not None:
            raise WorkspaceError("no-diagram-change review cannot contain a model")
        if self.architecture_impact not in {"diagram_change", "no_diagram_change"}:
            raise WorkspaceError("invalid architecture impact")
        self._require_artifact_identity(self.design.reference)
        if (self.design.reference.code_directory != self.code_directory or
                self.design.reference.design_owner_directory != self.design_owner_directory):
            raise WorkspaceError("design reference does not match recorded ownership")
        if self.proposed_model:
            for item in (self.proposed_model.contract, *self.proposed_model.sources):
                self._require_artifact_identity(item.reference)

    def _require_artifact_identity(self, reference: ArchitectureArtifactRef) -> None:
        if (reference.target_repository_key != self.target_repository_key or
                reference.destination_repository_key != self.documentation_repository_key or
                reference.destination_repository_role != self.documentation_repository_role):
            raise WorkspaceError("review artifact does not match fixed repositories")

    def _reviewed_tuple(self) -> dict[str, object]:
        return {"plan": self.plan.to_dict(), "design": self.design.to_dict(),
                "proposed_model": self.proposed_model.to_dict() if self.proposed_model else None,
                "requirement_citations": list(self.requirement_citations),
                "decision_citations": list(self.decision_citations),
                "view_citations": list(self.view_citations),
                "affected_work_ids": list(self.affected_work_ids),
                "architecture_impact": self.architecture_impact,
                "impact_reason": self.impact_reason}

    @property
    def reviewed_tuple_digest(self) -> str:
        payload = self.to_dict()
        del payload["status"]
        return _json_digest(payload)

    @property
    def review_unit_id(self) -> str:
        return f"architecture-review-{self.reviewed_tuple_digest}"

    def to_dict(self) -> dict[str, object]:
        return {"owner_work_id": self.owner_work_id, "authorized_owner": self.authorized_owner,
                "target_repository_key": self.target_repository_key,
                "code_directory": _portable_path(self.code_directory),
                "design_owner_directory": _portable_path(self.design_owner_directory),
                "code_repository_key": self.code_repository_key,
                "integration_lineage": self.integration_lineage,
                "documentation_repository_key": self.documentation_repository_key,
                "documentation_repository_role": self.documentation_repository_role,
                "documentation_destination_path": self.documentation_destination_path.as_posix(),
                "proposed_ancestor_context": self.proposed_ancestor_context.to_dict()
                if self.proposed_ancestor_context else None,
                "accepted_baseline": self.accepted_baseline.to_dict(),
                "baseline_pointer_id": self.baseline_pointer_id,
                "baseline_generation": self.baseline_generation,
                "rollout_version": self.rollout_version, "status": self.status,
                **self._reviewed_tuple()}

    @classmethod
    def from_dict(cls, value: object) -> "ArchitectureReviewUnit":
        fields = {"owner_work_id", "authorized_owner", "target_repository_key", "code_directory",
                  "design_owner_directory", "code_repository_key", "integration_lineage",
                  "documentation_repository_key", "documentation_repository_role",
                  "documentation_destination_path", "proposed_ancestor_context", "accepted_baseline",
                  "baseline_pointer_id", "baseline_generation", "rollout_version", "status", "plan",
                  "design", "proposed_model", "requirement_citations", "decision_citations",
                  "view_citations", "affected_work_ids", "architecture_impact", "impact_reason"}
        row = _mapping(value, fields)
        scalar_strings = fields - {"proposed_ancestor_context", "accepted_baseline",
                                  "baseline_pointer_id", "baseline_generation", "rollout_version",
                                  "plan", "design", "proposed_model", "requirement_citations",
                                  "decision_citations", "view_citations", "affected_work_ids"}
        if not all(isinstance(row[field], str) for field in scalar_strings):
            raise WorkspaceError("invalid architecture review unit")
        strings = {}
        for field in ("requirement_citations", "decision_citations", "view_citations", "affected_work_ids"):
            if not isinstance(row[field], list) or not all(isinstance(item, str) for item in row[field]):
                raise WorkspaceError("invalid architecture review unit")
            strings[field] = tuple(row[field])
        return cls(row["owner_work_id"], row["authorized_owner"], row["target_repository_key"],
                   _stored_path(row["code_directory"], allow_root=True),
                   _stored_path(row["design_owner_directory"], allow_root=True),
                   row["code_repository_key"], row["integration_lineage"],
                   row["documentation_repository_key"], row["documentation_repository_role"],
                   Path(row["documentation_destination_path"]),
                   ProposedAncestorContext.from_dict(row["proposed_ancestor_context"])
                   if row["proposed_ancestor_context"] is not None else None,
                   ArchitectureBaseline.from_dict(row["accepted_baseline"]), row["baseline_pointer_id"],
                   row["baseline_generation"], row["rollout_version"], row["status"],
                   PinnedDocumentRef.from_dict(row["plan"]),
                   PinnedArchitectureArtifact.from_dict(row["design"]),
                   ArchitectureModelBinding.from_dict(row["proposed_model"])
                   if row["proposed_model"] is not None else None,
                   strings["requirement_citations"], strings["decision_citations"],
                   strings["view_citations"], strings["affected_work_ids"],
                   row["architecture_impact"], row["impact_reason"])


@dataclass(frozen=True)
class AcceptedLineage:
    lineage_key: str
    generation: int
    accepted_review_unit_id: str
    accepted_tuple_digest: str
    accepted_code_head: str
    accepted_documentation_head: str
    accepted_design: PinnedArchitectureArtifact
    baseline: ArchitectureBaseline

    def __post_init__(self) -> None:
        _nonblank(self.lineage_key, "lineage key")
        _generation(self.generation, "accepted lineage generation", allow_none=False)
        _nonblank(self.accepted_review_unit_id, "accepted review unit ID")
        _digest(self.accepted_tuple_digest, "accepted review tuple")
        _revision(self.accepted_code_head, "accepted code head")
        _revision(self.accepted_documentation_head, "accepted documentation head")

    @property
    def pointer_id(self) -> str:
        return f"accepted-lineage-{_json_digest(self.to_dict())}"

    @property
    def lineage(self) -> str:
        return self.lineage_key

    @property
    def review_unit_id(self) -> str:
        return self.accepted_review_unit_id

    @property
    def integration_revision(self) -> str:
        return self.accepted_code_head

    def to_dict(self) -> dict[str, object]:
        return {"lineage_key": self.lineage_key, "generation": self.generation,
                "accepted_review_unit_id": self.accepted_review_unit_id,
                "accepted_tuple_digest": self.accepted_tuple_digest,
                "accepted_code_head": self.accepted_code_head,
                "accepted_documentation_head": self.accepted_documentation_head,
                "accepted_design": self.accepted_design.to_dict(), "baseline": self.baseline.to_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "AcceptedLineage":
        row = _mapping(value, {"lineage_key", "generation", "accepted_review_unit_id",
                               "accepted_tuple_digest", "accepted_code_head",
                               "accepted_documentation_head", "accepted_design", "baseline"})
        return cls(row["lineage_key"], row["generation"], row["accepted_review_unit_id"],
                   row["accepted_tuple_digest"], row["accepted_code_head"],
                   row["accepted_documentation_head"],
                   PinnedArchitectureArtifact.from_dict(row["accepted_design"]),
                   ArchitectureBaseline.from_dict(row["baseline"]))


AcceptedArchitecturePointer = AcceptedLineage


@dataclass(frozen=True)
class PromotionHeads:
    """Destination and incoming revisions fixed before promotion starts."""

    expected_code_head: str
    expected_documentation_head: str
    incoming_implementation_commit: str
    incoming_documentation_commit: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.expected_code_head, "expected code head"),
            (self.expected_documentation_head, "expected documentation head"),
            (self.incoming_implementation_commit, "incoming implementation commit"),
            (self.incoming_documentation_commit, "incoming documentation commit"),
        ):
            _revision(value, field)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> "PromotionHeads":
        row = _mapping(value, {
            "expected_code_head", "expected_documentation_head",
            "incoming_implementation_commit", "incoming_documentation_commit",
        })
        if not all(isinstance(item, str) for item in row.values()):
            raise WorkspaceError("invalid promotion heads")
        return cls(**row)


@dataclass(frozen=True)
class PromotionSide:
    state: PromotionSideState = "pending"
    observed_resulting_head: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"pending", "landed"}:
            raise WorkspaceError("invalid promotion side state")
        if self.state == "pending" and self.observed_resulting_head is not None:
            raise WorkspaceError("a pending promotion side cannot have a resulting head")
        if self.state == "landed":
            _revision(self.observed_resulting_head, "observed promotion head")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> "PromotionSide":
        row = _mapping(value, {"state", "observed_resulting_head"})
        return cls(row["state"], row["observed_resulting_head"])


@dataclass(frozen=True)
class PromotionJournal:
    """Durable reservation binding an approved tuple to exact Git revisions."""

    operation_id: str
    lineage_key: str
    reserved_generation: int | None
    approved_review_unit_id: str
    approved_tuple_digest: str
    code_repository_key: str
    documentation_repository_key: str
    documentation_repository_role: RepositoryRole
    documentation_destination_path: Path
    heads: PromotionHeads
    code: PromotionSide
    documentation: PromotionSide
    outcome: PromotionOutcome
    error_code: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.operation_id, "promotion operation ID"),
            (self.lineage_key, "promotion lineage"),
            (self.approved_review_unit_id, "approved review unit ID"),
            (self.code_repository_key, "code repository key"),
            (self.documentation_repository_key, "documentation repository key"),
        ):
            _nonblank(value, field)
        _generation(self.reserved_generation, "reserved lineage generation")
        _digest(self.approved_tuple_digest, "approved review tuple")
        _role(self.documentation_repository_role)
        _relative_path(
            self.documentation_destination_path,
            "documentation destination",
            allow_root=True,
        )
        if self.outcome not in {"reserved", "acceptance_pending", "accepted", "conflict"}:
            raise WorkspaceError("invalid promotion outcome")
        if self.outcome == "conflict":
            _nonblank(self.error_code, "promotion conflict code")
        elif self.error_code is not None:
            raise WorkspaceError("only a conflicted promotion has an error code")

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "lineage_key": self.lineage_key,
            "reserved_generation": self.reserved_generation,
            "approved_review_unit_id": self.approved_review_unit_id,
            "approved_tuple_digest": self.approved_tuple_digest,
            "code_repository_key": self.code_repository_key,
            "documentation_repository_key": self.documentation_repository_key,
            "documentation_repository_role": self.documentation_repository_role,
            "documentation_destination_path": self.documentation_destination_path.as_posix(),
            "heads": self.heads.to_dict(),
            "code": self.code.to_dict(),
            "documentation": self.documentation.to_dict(),
            "outcome": self.outcome,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PromotionJournal":
        row = _mapping(value, {
            "operation_id", "lineage_key", "reserved_generation",
            "approved_review_unit_id", "approved_tuple_digest", "code_repository_key",
            "documentation_repository_key", "documentation_repository_role",
            "documentation_destination_path", "heads", "code", "documentation",
            "outcome", "error_code",
        })
        return cls(
            row["operation_id"], row["lineage_key"], row["reserved_generation"],
            row["approved_review_unit_id"], row["approved_tuple_digest"],
            row["code_repository_key"], row["documentation_repository_key"],
            row["documentation_repository_role"], Path(row["documentation_destination_path"]),
            PromotionHeads.from_dict(row["heads"]), PromotionSide.from_dict(row["code"]),
            PromotionSide.from_dict(row["documentation"]), row["outcome"], row["error_code"],
        )


@dataclass(frozen=True)
class ReviewBaselineStatus:
    current: AcceptedLineage | None
    stale: bool
    rebase_required: bool


@dataclass(frozen=True)
class ArchitectureReviewRecord:
    review_unit_id: str
    reviewer: str
    reviewed_at: str
    tuple_digest: str
    decision: ReviewDecision

    def __post_init__(self) -> None:
        _nonblank(self.review_unit_id, "review unit ID")
        _nonblank(self.reviewer, "architecture reviewer")
        _nonblank(self.reviewed_at, "architecture review time")
        _digest(self.tuple_digest, "review tuple")
        if self.decision not in {"reviewed", "rejected"}:
            raise WorkspaceError("invalid architecture review decision")

    def to_dict(self) -> dict[str, str]:
        return {
            "review_unit_id": self.review_unit_id,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "tuple_digest": self.tuple_digest,
            "decision": self.decision,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ArchitectureReviewRecord":
        row = _mapping(
            value,
            {"review_unit_id", "reviewer", "reviewed_at", "tuple_digest", "decision"},
        )
        if not all(isinstance(item, str) for item in row.values()):
            raise WorkspaceError("invalid architecture review record")
        return cls(
            row["review_unit_id"],
            row["reviewer"],
            row["reviewed_at"],
            row["tuple_digest"],
            row["decision"],
        )


@dataclass(frozen=True)
class ArchitectureProposalState:
    unit: ArchitectureReviewUnit | None
    accepted: AcceptedLineage | None
    review: ArchitectureReviewRecord | None
    semantic_diff: C4SemanticDiff | None
    invalidation_reasons: tuple[str, ...] = ()
    pending_promotion: PromotionJournal | None = None

    @property
    def status(self) -> ReviewStatus | None:
        return self.unit.status if self.unit else None


@dataclass(frozen=True)
class ReviewGateResult:
    """The exact policy and reviewed tuple admitted at a lifecycle boundary."""

    work_id: str
    boundary: ReviewGateBoundary
    gate_name: str
    rollout_version: int
    review_unit_id: str | None
    tuple_digest: str | None


class ArchitectureReviewStore:
    def __init__(self, project: ProjectContext, path: Path | None = None) -> None:
        self.project = project
        self.path = path or project.target.root / "architecture" / "review-units.json"

    def save(self, unit: ArchitectureReviewUnit) -> str:
        self._validate_unit_inputs(unit)
        state = self._read()
        identity, encoded = unit.review_unit_id, unit.to_dict()
        existing = state["review_units"].get(identity)
        if existing is not None:
            persisted = ArchitectureReviewUnit.from_dict(existing)
            if persisted.reviewed_tuple_digest != unit.reviewed_tuple_digest:
                raise WorkspaceError("architecture review unit identity collision")
            if persisted.status != unit.status:
                raise WorkspaceError("architecture review status must use the review operation")
            return identity
        state["review_units"][identity] = encoded
        state["review_order"].append(identity)
        self._write(state)
        return identity

    def get(self, review_unit_id: str) -> ArchitectureReviewUnit | None:
        value = self._read()["review_units"].get(review_unit_id)
        return ArchitectureReviewUnit.from_dict(value) if value is not None else None

    def get_review(self, review_unit_id: str) -> ArchitectureReviewRecord | None:
        value = self._read()["reviews"].get(review_unit_id)
        return ArchitectureReviewRecord.from_dict(value) if value is not None else None

    def get_diff(self, review_unit_id: str) -> C4SemanticDiff | None:
        value = self._read()["diffs"].get(review_unit_id)
        return _semantic_diff_from_dict(value) if value is not None else None

    def get_invalidation_reasons(self, review_unit_id: str) -> tuple[str, ...]:
        values = self._read()["invalidations"].get(review_unit_id, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise WorkspaceError("invalid architecture review invalidation record")
        return tuple(values)

    def mark_stale(self, review_unit_id: str, reason: str) -> ArchitectureReviewUnit:
        """Invalidate a unit without discarding its human review evidence or diff."""

        if reason not in {"artifact_changed", "destination_changed", "stale_baseline"}:
            raise WorkspaceError("invalid architecture review invalidation reason")
        state = self._read()
        value = state["review_units"].get(review_unit_id)
        if value is None:
            raise ArchitectureProposalError("review_required", "unknown architecture review unit")
        unit = ArchitectureReviewUnit.from_dict(value)
        if unit.status == "rejected":
            return unit
        updated = replace(unit, status="stale")
        reasons = state["invalidations"].setdefault(review_unit_id, [])
        if reason not in reasons:
            reasons.append(reason)
        state["review_units"][review_unit_id] = updated.to_dict()
        self._write(state)
        return updated

    def refresh(
        self, review_unit_id: str, *, lineage_revision: str | None = None
    ) -> ArchitectureReviewUnit:
        """Recheck a unit at a lifecycle boundary without renewing its review."""

        unit = self.get(review_unit_id)
        if unit is None:
            raise ArchitectureProposalError("review_required", "unknown architecture review unit")
        return _refresh_review_unit(self, unit, lineage_revision=lineage_revision)

    def save_diff(self, review_unit_id: str, diff: C4SemanticDiff) -> None:
        state = self._read()
        if review_unit_id not in state["review_units"]:
            raise WorkspaceError("cannot attach a diff to an unknown architecture review unit")
        encoded = asdict(diff)
        existing = state["diffs"].get(review_unit_id)
        if existing is not None and existing != encoded:
            raise WorkspaceError("architecture review semantic diff changed")
        state["diffs"][review_unit_id] = encoded
        self._write(state)

    def save_staged(
        self, unit: ArchitectureReviewUnit, diff: C4SemanticDiff
    ) -> str:
        """Persist a staged tuple and its review diff in one durable replacement."""

        self._validate_unit_inputs(unit)
        if unit.status != "staged":
            raise WorkspaceError("only a staged architecture unit can include a review diff")
        state = self._read()
        identity = unit.review_unit_id
        encoded_unit = unit.to_dict()
        encoded_diff = asdict(diff)
        existing = state["review_units"].get(identity)
        if existing is not None and existing != encoded_unit:
            raise WorkspaceError("architecture review unit identity collision")
        existing_diff = state["diffs"].get(identity)
        if existing_diff is not None and existing_diff != encoded_diff:
            raise WorkspaceError("architecture review semantic diff changed")
        state["review_units"][identity] = encoded_unit
        state["diffs"][identity] = encoded_diff
        if existing is None:
            state["review_order"].append(identity)
        self._write(state)
        return identity

    def find_for_owner(
        self, owner: str, work_id: str, lineage: str
    ) -> ArchitectureReviewUnit | None:
        _nonblank(owner, "architecture owner")
        _nonblank(work_id, "owner work ID")
        _nonblank(lineage, "integration lineage")
        matches: list[ArchitectureReviewUnit] = []
        for unit in self._units_in_order():
            if unit.owner_work_id == work_id and unit.integration_lineage == lineage:
                if unit.authorized_owner != owner:
                    raise ArchitectureProposalError(
                        "owner_denied", "architecture proposal belongs to another owner"
                    )
                matches.append(unit)
        if not matches:
            return None
        # Store serialization sorts object keys, so dict order is not review
        # chronology.  The accepted-lineage CAS is the durable ordering: prefer
        # a proposal based on its current pointer over a now-stale predecessor.
        current = [unit for unit in matches if not self.baseline_status(unit).stale]
        return (current or matches)[-1]

    def record_review(
        self,
        review_unit_id: str,
        *,
        reviewer: str,
        decision: ReviewDecision,
        reviewed_at: str,
    ) -> ArchitectureReviewUnit:
        state = self._read()
        value = state["review_units"].get(review_unit_id)
        if value is None:
            raise ArchitectureProposalError("review_required", "unknown architecture review unit")
        unit = ArchitectureReviewUnit.from_dict(value)
        status: ReviewStatus = "reviewed" if decision == "reviewed" else "rejected"
        updated = replace(unit, status=status)
        record = ArchitectureReviewRecord(
            review_unit_id, reviewer, reviewed_at, unit.reviewed_tuple_digest, decision
        )
        existing = state["reviews"].get(review_unit_id)
        if existing is not None:
            durable = ArchitectureReviewRecord.from_dict(existing)
            if durable != record:
                raise ArchitectureProposalError(
                    "review_required", "architecture review unit was already decided"
                )
            return updated
        state["review_units"][review_unit_id] = updated.to_dict()
        state["reviews"][review_unit_id] = record.to_dict()
        self._write(state)
        return updated

    def enable_gate_rollout(self, version: int) -> None:
        """Explicitly activate a monotonic lifecycle gate version."""

        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise WorkspaceError("review gate rollout version must be a positive integer")
        state = self._read()
        rollout = state["gate_rollout"]
        active = rollout["active_version"]
        if active is not None and version < active:
            raise WorkspaceError("review gate rollout version cannot move backwards")
        rollout["active_version"] = version
        self._write(state)

    def gate_rollout_version(self) -> int | None:
        return self._read()["gate_rollout"]["active_version"]

    def gate_policy_version(self, work_id: str) -> int | None:
        _nonblank(work_id, "review gate work ID")
        return self._read()["gate_rollout"]["work_policies"].get(work_id)

    def bind_gate_policy(self, work_id: str, version: int) -> int:
        """Record policy once; zero is the durable pre-rollout policy."""

        _nonblank(work_id, "review gate work ID")
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise WorkspaceError("invalid review gate policy version")
        state = self._read()
        policies = state["gate_rollout"]["work_policies"]
        existing = policies.get(work_id)
        if existing is not None:
            return existing
        policies[work_id] = version
        self._write(state)
        return version

    def rebind_gate_policy(self, work_id: str, version: int) -> int:
        """Bind a materially revised proposal to the current rollout."""

        _nonblank(work_id, "review gate work ID")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise WorkspaceError("invalid review gate policy version")
        state = self._read()
        existing = state["gate_rollout"]["work_policies"].get(work_id)
        if existing is not None and existing > version:
            raise WorkspaceError("review gate policy version cannot move backwards")
        state["gate_rollout"]["work_policies"][work_id] = version
        self._write(state)
        return version

    def set_acceptance_hold(self, work_ids: Sequence[str], operation_id: str | None) -> None:
        """Hold or release exactly the work affected by a partial promotion."""

        ids = tuple(work_ids)
        _unique_nonblank(ids, "acceptance hold work IDs")
        if operation_id is not None:
            _nonblank(operation_id, "promotion operation ID")
        state = self._read()
        holds = state["gate_rollout"]["acceptance_holds"]
        for work_id in ids:
            if operation_id is None:
                holds.pop(work_id, None)
            else:
                holds[work_id] = operation_id
        self._write(state)

    def acceptance_hold(self, work_id: str) -> str | None:
        _nonblank(work_id, "acceptance hold work ID")
        value = self._read()["gate_rollout"]["acceptance_holds"].get(work_id)
        if value is not None and not isinstance(value, str):
            raise WorkspaceError("invalid architecture acceptance hold")
        return value

    def get_promotion(self, operation_id: str) -> PromotionJournal | None:
        _nonblank(operation_id, "promotion operation ID")
        value = self._read()["promotions"].get(operation_id)
        return PromotionJournal.from_dict(value) if value is not None else None

    def pending_promotion(self, lineage: str) -> PromotionJournal | None:
        _nonblank(lineage, "integration lineage")
        state = self._read()
        operation_id = state["promotion_reservations"].get(lineage)
        if operation_id is None:
            return None
        value = state["promotions"].get(operation_id)
        if value is None:
            raise WorkspaceError("invalid architecture promotion reservation")
        journal = PromotionJournal.from_dict(value)
        if journal.outcome not in {"reserved", "acceptance_pending"}:
            raise WorkspaceError("terminal architecture promotion remains reserved")
        return journal

    def reserve_promotion(
        self,
        review_unit_id: str,
        expected_heads: PromotionHeads | Mapping[str, str],
        expected_generation: int | None,
        *,
        operation_id: str | None = None,
    ) -> PromotionJournal:
        """Atomically reserve one approved tuple at the current lineage generation."""

        heads = _promotion_heads(expected_heads)
        unit = self.get(review_unit_id)
        if unit is None:
            raise ArchitectureProposalError("review_required", "unknown architecture review unit")
        unit = self.refresh(review_unit_id, lineage_revision=heads.expected_code_head)
        if unit.status != "approved":
            raise ArchitectureProposalError(
                "review_required", "architecture proposal is not approved for promotion"
            )
        if unit.reviewed_tuple_digest != review_unit_id.removeprefix("architecture-review-"):
            raise ArchitectureProposalError("artifact_changed", "approved tuple identity changed")

        payload = {
            "review_unit_id": review_unit_id,
            "tuple_digest": unit.reviewed_tuple_digest,
            "lineage": unit.integration_lineage,
            "reserved_generation": expected_generation,
            "heads": heads.to_dict(),
        }
        generated_id = f"architecture-promotion-{_json_digest(payload)}"
        if operation_id is None:
            operation_id = generated_id
        else:
            _nonblank(operation_id, "promotion operation ID")

        # The shared lifecycle lock protects reservation, generation, and head
        # comparisons. It is released before the later promotion adapter does
        # any rendering, merging, or remote Git work.
        from cascade.task.lifecycle_lock import task_lifecycle_lock

        with task_lifecycle_lock(root=self.project.target.root):
            state = self._read()
            durable_value = state["review_units"].get(review_unit_id)
            if durable_value is None:
                raise ArchitectureProposalError(
                    "review_required", "unknown architecture review unit"
                )
            durable = ArchitectureReviewUnit.from_dict(durable_value)
            if durable.status != "approved" or durable.reviewed_tuple_digest != unit.reviewed_tuple_digest:
                raise ArchitectureProposalError(
                    "artifact_changed", "approved architecture tuple changed before reservation"
                )

            docs = _architecture_repository(
                self.project,
                durable.documentation_repository_role,
                durable.documentation_repository_key,
            )
            _require_commit(self.project.target.root, heads.expected_code_head, "expected code head")
            _require_commit(docs.root, heads.expected_documentation_head,
                            "expected documentation head")
            _require_commit(self.project.target.root, heads.incoming_implementation_commit,
                            "incoming implementation commit")
            _require_commit(docs.root, heads.incoming_documentation_commit,
                            "incoming documentation commit")
            if _head(self.project.target.root) != heads.expected_code_head:
                raise ArchitectureProposalError("head_conflict", "code destination head changed")
            if _head(docs.root) != heads.expected_documentation_head:
                raise ArchitectureProposalError(
                    "head_conflict", "documentation destination head changed"
                )

            current = self.resolve_current(
                durable.integration_lineage, lineage_revision=heads.expected_code_head
            )
            actual_generation = current.generation if current else None
            if actual_generation != expected_generation:
                raise ArchitectureProposalError(
                    "reservation_lost", "accepted lineage generation changed"
                )
            if self.baseline_status(
                durable, lineage_revision=heads.expected_code_head
            ).stale:
                raise ArchitectureProposalError(
                    "stale_baseline", "approved tuple is based on a stale accepted lineage"
                )

            existing_value = state["promotions"].get(operation_id)
            if existing_value is not None:
                existing = PromotionJournal.from_dict(existing_value)
                candidate = _new_promotion_journal(operation_id, durable, heads,
                                                   expected_generation)
                if _same_promotion_identity(existing, candidate):
                    return existing
                raise ArchitectureProposalError(
                    "promotion_conflict", "promotion operation ID has different revisions"
                )

            incumbent_id = state["promotion_reservations"].get(durable.integration_lineage)
            journal = _new_promotion_journal(
                operation_id, durable, heads, expected_generation
            )
            if incumbent_id is not None and incumbent_id != operation_id:
                conflict = replace(
                    journal, outcome="conflict", error_code="promotion_conflict"
                )
                state["promotions"][operation_id] = conflict.to_dict()
                self._write(state)
                return conflict

            state["promotions"][operation_id] = journal.to_dict()
            state["promotion_reservations"][durable.integration_lineage] = operation_id
            holds = state["gate_rollout"]["acceptance_holds"]
            for work_id in durable.affected_work_ids:
                holds[work_id] = operation_id
            self._write(state)
            return journal

    def promote_or_resume(self, operation_id: str) -> PromotionJournal:
        """Land the exact journaled revisions and atomically accept both sides."""

        _nonblank(operation_id, "promotion operation ID")
        journal = self.get_promotion(operation_id)
        if journal is None:
            raise ArchitectureProposalError("promotion_conflict", "unknown promotion operation")
        if journal.outcome in {"accepted", "conflict"}:
            return journal
        unit = self.get(journal.approved_review_unit_id)
        if unit is None:
            return self._conflict_promotion(operation_id, "review_required")
        code_root = self.project.target.root
        docs_root = _architecture_repository(
            self.project,
            journal.documentation_repository_role,
            journal.documentation_repository_key,
        ).root

        if code_root.resolve() == docs_root.resolve():
            current = _head(code_root)
            incoming = (
                journal.heads.incoming_implementation_commit,
                journal.heads.incoming_documentation_commit,
            )
            if not all(_is_ancestor(code_root, revision, current) for revision in incoming):
                if current != journal.heads.expected_code_head:
                    return self._conflict_promotion(operation_id, "head_conflict")
                if not self._promotion_is_current(journal, unit, current):
                    return self.get_promotion(operation_id)  # type: ignore[return-value]
                if not _merge_promotion_commits(code_root, incoming):
                    return self._conflict_promotion(operation_id, "merge_conflict")
                current = _head(code_root)
            journal = self._record_promotion_sides(
                operation_id, code_head=current, documentation_head=current
            )
        else:
            if journal.code.state == "pending":
                journal = self._land_promotion_side(
                    journal, unit, "code", code_root,
                    journal.heads.expected_code_head,
                    journal.heads.incoming_implementation_commit,
                )
                if journal.outcome == "conflict":
                    return journal
            if journal.documentation.state == "pending":
                journal = self._land_promotion_side(
                    journal, unit, "documentation", docs_root,
                    journal.heads.expected_documentation_head,
                    journal.heads.incoming_documentation_commit,
                )
                if journal.outcome == "conflict":
                    return journal

        code_head = journal.code.observed_resulting_head
        if code_head is None:
            return journal
        refreshed = self.refresh(unit.review_unit_id, lineage_revision=code_head)
        if (refreshed.status != "approved" or
                refreshed.reviewed_tuple_digest != journal.approved_tuple_digest):
            return self._conflict_promotion(operation_id, "artifact_changed")
        return self._finalize_promotion(operation_id)

    def _land_promotion_side(
        self,
        journal: PromotionJournal,
        unit: ArchitectureReviewUnit,
        side: Literal["code", "documentation"],
        repository: Path,
        expected_head: str,
        incoming_commit: str,
    ) -> PromotionJournal:
        current = _head(repository)
        if not _is_ancestor(repository, incoming_commit, current):
            if current != expected_head:
                return self._conflict_promotion(journal.operation_id, "head_conflict")
            code_head = current if side == "code" else _head(self.project.target.root)
            if not self._promotion_is_current(journal, unit, code_head):
                return self.get_promotion(journal.operation_id)  # type: ignore[return-value]
            if not _merge_promotion_commits(repository, (incoming_commit,)):
                return self._conflict_promotion(journal.operation_id, "merge_conflict")
            current = _head(repository)
        return self._record_promotion_sides(
            journal.operation_id,
            code_head=current if side == "code" else None,
            documentation_head=current if side == "documentation" else None,
        )

    def _promotion_is_current(
        self, journal: PromotionJournal, unit: ArchitectureReviewUnit, code_head: str
    ) -> bool:
        """Recheck tuple, reservation and generation immediately before Git work."""

        refreshed = self.refresh(unit.review_unit_id, lineage_revision=code_head)
        if (refreshed.status != "approved" or
                refreshed.reviewed_tuple_digest != journal.approved_tuple_digest):
            self._conflict_promotion(journal.operation_id, "artifact_changed")
            return False
        from cascade.task.lifecycle_lock import task_lifecycle_lock

        with task_lifecycle_lock(root=self.project.target.root):
            state = self._read()
            if state["promotion_reservations"].get(journal.lineage_key) != journal.operation_id:
                self._set_promotion_conflict(state, journal, "reservation_lost")
                self._write(state)
                return False
            current = self.resolve_current(journal.lineage_key, lineage_revision=code_head)
            if (current.generation if current else None) != journal.reserved_generation:
                self._set_promotion_conflict(state, journal, "reservation_lost")
                self._write(state)
                return False
        return True

    def _record_promotion_sides(
        self,
        operation_id: str,
        *,
        code_head: str | None = None,
        documentation_head: str | None = None,
    ) -> PromotionJournal:
        """Persist post-Git evidence without assuming the reservation survived Git."""

        from cascade.task.lifecycle_lock import task_lifecycle_lock

        with task_lifecycle_lock(root=self.project.target.root):
            state = self._read()
            journal = PromotionJournal.from_dict(state["promotions"][operation_id])
            if journal.outcome in {"accepted", "conflict"}:
                return journal
            if state["promotion_reservations"].get(journal.lineage_key) != operation_id:
                return self._set_promotion_conflict(state, journal, "reservation_lost", write=True)
            current = self.resolve_current(
                journal.lineage_key, lineage_revision=code_head or _head(self.project.target.root)
            )
            if (current.generation if current else None) != journal.reserved_generation:
                return self._set_promotion_conflict(state, journal, "reservation_lost", write=True)
            updated = replace(
                journal,
                code=(PromotionSide("landed", code_head) if code_head else journal.code),
                documentation=(PromotionSide("landed", documentation_head)
                               if documentation_head else journal.documentation),
                outcome="acceptance_pending",
            )
            state["promotions"][operation_id] = updated.to_dict()
            self._write(state)
            return updated

    def _finalize_promotion(self, operation_id: str) -> PromotionJournal:
        from cascade.task.lifecycle_lock import task_lifecycle_lock

        with task_lifecycle_lock(root=self.project.target.root):
            state = self._read()
            journal = PromotionJournal.from_dict(state["promotions"][operation_id])
            if journal.outcome in {"accepted", "conflict"}:
                return journal
            if journal.code.state != "landed" or journal.documentation.state != "landed":
                return journal
            if state["promotion_reservations"].get(journal.lineage_key) != operation_id:
                return self._set_promotion_conflict(state, journal, "reservation_lost", write=True)
            code_head = journal.code.observed_resulting_head
            documentation_head = journal.documentation.observed_resulting_head
            assert code_head is not None and documentation_head is not None
            current = self.resolve_current(journal.lineage_key, lineage_revision=code_head)
            if (current.generation if current else None) != journal.reserved_generation:
                return self._set_promotion_conflict(state, journal, "reservation_lost", write=True)
            unit = ArchitectureReviewUnit.from_dict(
                state["review_units"][journal.approved_review_unit_id]
            )
            if (unit.status != "approved" or
                    unit.reviewed_tuple_digest != journal.approved_tuple_digest):
                return self._set_promotion_conflict(state, journal, "artifact_changed", write=True)
            baseline = (ArchitectureBaseline("model", unit.proposed_model, unit.review_unit_id)
                        if unit.architecture_impact == "diagram_change" else unit.accepted_baseline)
            pointer = AcceptedLineage(
                journal.lineage_key,
                (journal.reserved_generation or 0) + 1,
                unit.review_unit_id,
                unit.reviewed_tuple_digest,
                code_head,
                documentation_head,
                unit.design,
                baseline,
            )
            accepted = replace(journal, outcome="accepted")
            state["lineages"].setdefault(journal.lineage_key, []).append(pointer.to_dict())
            state["promotions"][operation_id] = accepted.to_dict()
            state["promotion_reservations"].pop(journal.lineage_key, None)
            holds = state["gate_rollout"]["acceptance_holds"]
            for work_id in unit.affected_work_ids:
                if holds.get(work_id) == operation_id:
                    holds.pop(work_id)
            self._write(state)
            return accepted

    def _conflict_promotion(self, operation_id: str, code: str) -> PromotionJournal:
        from cascade.task.lifecycle_lock import task_lifecycle_lock

        with task_lifecycle_lock(root=self.project.target.root):
            state = self._read()
            journal = PromotionJournal.from_dict(state["promotions"][operation_id])
            return self._set_promotion_conflict(state, journal, code, write=True)

    def _set_promotion_conflict(
        self, state: dict[str, object], journal: PromotionJournal, code: str, *,
        write: bool = False,
    ) -> PromotionJournal:
        conflicted = replace(journal, outcome="conflict", error_code=code)
        state["promotions"][journal.operation_id] = conflicted.to_dict()
        if state["promotion_reservations"].get(journal.lineage_key) == journal.operation_id:
            state["promotion_reservations"].pop(journal.lineage_key)
        if write:
            self._write(state)
        return conflicted

    def approve_review_unit(self, review_unit_id: str) -> ArchitectureReviewUnit:
        """Pin the human-reviewed tuple at the existing lifecycle approval boundary."""

        state = self._read()
        value = state["review_units"].get(review_unit_id)
        if value is None:
            raise ArchitectureProposalError("review_required", "unknown architecture review unit")
        unit = ArchitectureReviewUnit.from_dict(value)
        if unit.status == "approved":
            return unit
        review = self.get_review(review_unit_id)
        if unit.status != "reviewed" or review is None or review.decision != "reviewed":
            raise ArchitectureProposalError(
                "review_required", "architecture proposal requires human review before approval"
            )
        if review.tuple_digest != unit.reviewed_tuple_digest:
            raise ArchitectureProposalError("artifact_changed", "human review does not match tuple")
        updated = replace(unit, status="approved")
        state["review_units"][review_unit_id] = updated.to_dict()
        self._write(state)
        return updated

    def units_affecting(self, work_id: str) -> tuple[ArchitectureReviewUnit, ...]:
        _nonblank(work_id, "review gate work ID")
        units = self._units_in_order()
        return tuple(
            unit for unit in units
            if unit.owner_work_id == work_id or work_id in unit.affected_work_ids
        )

    def _units_in_order(self) -> tuple[ArchitectureReviewUnit, ...]:
        state = self._read()
        order = list(state["review_order"])
        order.extend(
            unit_id for unit_id in state["review_units"] if unit_id not in order
        )
        return tuple(
            ArchitectureReviewUnit.from_dict(state["review_units"][unit_id])
            for unit_id in order
        )

    def resolve_current(self, lineage: str, *, lineage_revision: str | None = None) -> AcceptedLineage | None:
        _nonblank(lineage, "integration lineage")
        revision = lineage_revision or _head(self.project.target.root)
        _revision(revision, "lineage")
        for value in reversed(self._read()["lineages"].get(lineage, [])):
            pointer = AcceptedLineage.from_dict(value)
            if _is_ancestor(self.project.target.root, pointer.accepted_code_head, revision):
                return pointer
        return None

    def baseline_status(self, unit: ArchitectureReviewUnit, *,
                        lineage_revision: str | None = None) -> ReviewBaselineStatus:
        current = self.resolve_current(unit.integration_lineage, lineage_revision=lineage_revision)
        if current is None:
            stale = not (unit.accepted_baseline == ArchitectureBaseline.empty() and
                         unit.baseline_pointer_id is None and unit.baseline_generation is None)
        else:
            stale = (unit.baseline_pointer_id != current.pointer_id or
                     unit.baseline_generation != current.generation or
                     unit.accepted_baseline != current.baseline)
        return ReviewBaselineStatus(current, stale, stale)

    def accept(self, review_unit_id: str, *, accepted_code_head: str | None = None,
               accepted_documentation_head: str | None = None,
               integration_revision: str | None = None,
               expected_generation: int | None) -> AcceptedLineage:
        """Advance an unreserved lineage using a lifecycle-locked generation CAS."""

        from cascade.task.lifecycle_lock import task_lifecycle_lock

        with task_lifecycle_lock(root=self.project.target.root):
            return self._accept_locked(
                review_unit_id,
                accepted_code_head=accepted_code_head,
                accepted_documentation_head=accepted_documentation_head,
                integration_revision=integration_revision,
                expected_generation=expected_generation,
            )

    def _accept_locked(self, review_unit_id: str, *, accepted_code_head: str | None = None,
                       accepted_documentation_head: str | None = None,
                       integration_revision: str | None = None,
                       expected_generation: int | None) -> AcceptedLineage:
        unit = self.get(review_unit_id)
        if unit is None:
            raise WorkspaceError("unknown architecture review unit")
        if self.pending_promotion(unit.integration_lineage) is not None:
            raise ArchitectureProposalError(
                "acceptance_pending",
                "a reserved promotion must finalize through its journal",
            )
        if integration_revision is not None:
            if accepted_code_head is not None or accepted_documentation_head is not None:
                raise WorkspaceError("provide accepted heads or integration revision, not both")
            accepted_code_head = accepted_documentation_head = integration_revision
        if accepted_code_head is None or accepted_documentation_head is None:
            raise WorkspaceError("acceptance requires exact code and documentation heads")
        _require_commit(self.project.target.root, accepted_code_head, "accepted code head")
        docs = _architecture_repository(
            self.project,
            unit.documentation_repository_role,
            unit.documentation_repository_key,
        )
        _require_commit(docs.root, accepted_documentation_head, "accepted documentation head")
        current = self.resolve_current(unit.integration_lineage, lineage_revision=accepted_code_head)
        if (current is not None and current.accepted_review_unit_id == review_unit_id and
                current.accepted_code_head == accepted_code_head and
                current.accepted_documentation_head == accepted_documentation_head):
            return current
        actual_generation = current.generation if current else None
        if actual_generation != expected_generation:
            raise WorkspaceError("accepted architecture baseline generation changed")
        if self.baseline_status(unit, lineage_revision=accepted_code_head).stale:
            raise WorkspaceError("architecture review unit has a stale accepted baseline")
        baseline = (ArchitectureBaseline("model", unit.proposed_model, review_unit_id)
                    if unit.architecture_impact == "diagram_change" else unit.accepted_baseline)
        pointer = AcceptedLineage(unit.integration_lineage, (actual_generation or 0) + 1,
                                  review_unit_id, unit.reviewed_tuple_digest,
                                  accepted_code_head, accepted_documentation_head,
                                  unit.design, baseline)
        state = self._read()
        durable = self.resolve_current(unit.integration_lineage, lineage_revision=accepted_code_head)
        if (durable.generation if durable else None) != actual_generation:
            raise WorkspaceError("accepted architecture baseline generation changed")
        state["lineages"].setdefault(unit.integration_lineage, []).append(pointer.to_dict())
        self._write(state)
        return pointer

    def _validate_unit_inputs(self, unit: ArchitectureReviewUnit) -> None:
        if unit.target_repository_key != self.project.target_repository_key:
            raise WorkspaceError("architecture review unit belongs to another target")
        if unit.code_repository_key != self.project.target.repository_key:
            raise WorkspaceError("architecture review unit has a different code repository")
        expected_key = (self.project.target_repository_key if self.project.architecture_destination == "target"
                        else self.project.architecture_repository.repository_key)
        if (unit.documentation_repository_role != self.project.architecture_destination or
                unit.documentation_repository_key != expected_key or
                unit.documentation_destination_path != Path(".")):
            raise WorkspaceError("architecture review unit destination differs from current configuration")
        _verify_digest(_read_pinned_document(self.project, unit.plan), unit.plan.content_digest)
        artifacts = [unit.design]
        if unit.proposed_model:
            artifacts.extend((unit.proposed_model.contract, *unit.proposed_model.sources))
        for artifact in artifacts:
            _verify_digest(_read_architecture_bytes(self.project, artifact.reference),
                           artifact.content_digest)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {
                "version": _SCHEMA_VERSION,
                "review_units": {},
                "review_order": [],
                "lineages": {},
                "reviews": {},
                "diffs": {},
                "invalidations": {},
                "gate_rollout": {
                    "name": _REVIEW_GATE_NAME,
                    "active_version": None,
                    "work_policies": {},
                    "acceptance_holds": {},
                },
                "promotions": {},
                "promotion_reservations": {},
            }
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"invalid architecture review store: {self.path}") from exc
        if (not isinstance(state, dict) or
                not {"version", "review_units", "lineages"}.issubset(state) or
                not set(state).issubset({"version", "review_units", "review_order", "lineages", "reviews", "diffs",
                                         "invalidations", "gate_rollout", "promotions",
                                         "promotion_reservations"}) or
                state["version"] != _SCHEMA_VERSION or not isinstance(state["review_units"], dict) or
                not isinstance(state["lineages"], dict)):
            raise WorkspaceError(f"unsupported architecture review store: {self.path}")
        state.setdefault("reviews", {})
        state.setdefault("review_order", [])
        state.setdefault("diffs", {})
        state.setdefault("invalidations", {})
        state.setdefault("promotions", {})
        state.setdefault("promotion_reservations", {})
        state.setdefault(
            "gate_rollout",
            {"name": _REVIEW_GATE_NAME, "active_version": None,
             "work_policies": {}, "acceptance_holds": {}},
        )
        if not isinstance(state["gate_rollout"], dict):
            raise WorkspaceError(f"unsupported architecture review store: {self.path}")
        state["gate_rollout"].setdefault("name", _REVIEW_GATE_NAME)
        state["gate_rollout"].setdefault("acceptance_holds", {})
        if (not isinstance(state["reviews"], dict) or not isinstance(state["diffs"], dict) or
                not isinstance(state["review_order"], list) or
                len(state["review_order"]) != len(set(state["review_order"])) or
                not all(isinstance(item, str) and item in state["review_units"]
                        for item in state["review_order"]) or
                not isinstance(state["invalidations"], dict) or
                not isinstance(state["promotions"], dict) or
                not isinstance(state["promotion_reservations"], dict) or
                not isinstance(state["gate_rollout"], dict) or
                set(state["gate_rollout"]) != {
                    "name", "active_version", "work_policies", "acceptance_holds"
                } or
                state["gate_rollout"]["name"] != _REVIEW_GATE_NAME or
                not isinstance(state["gate_rollout"]["work_policies"], dict) or
                not isinstance(state["gate_rollout"]["acceptance_holds"], dict)):
            raise WorkspaceError(f"unsupported architecture review store: {self.path}")
        active = state["gate_rollout"]["active_version"]
        if active is not None and (
            not isinstance(active, int) or isinstance(active, bool) or active < 1
        ):
            raise WorkspaceError(f"unsupported architecture review store: {self.path}")
        return state

    def _write(self, state: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def read_architecture_state(
    project: ProjectContext,
    *,
    owner: str,
    work_id: str,
    lineage: str,
    store: ArchitectureReviewStore | None = None,
    lineage_revision: str | None = None,
) -> ArchitectureProposalState:
    """Inspect only the proposal owned by ``owner`` for one integration lineage."""

    review_store = store or ArchitectureReviewStore(project)
    unit = review_store.find_for_owner(owner, work_id, lineage)
    if unit is not None:
        unit = review_store.refresh(unit.review_unit_id, lineage_revision=lineage_revision)
    accepted = review_store.resolve_current(lineage, lineage_revision=lineage_revision)
    return ArchitectureProposalState(
        unit,
        accepted,
        review_store.get_review(unit.review_unit_id) if unit else None,
        review_store.get_diff(unit.review_unit_id) if unit else None,
        review_store.get_invalidation_reasons(unit.review_unit_id) if unit else (),
        review_store.pending_promotion(lineage),
    )


def reserve_promotion(
    project: ProjectContext,
    unit_id: str,
    expected_heads: PromotionHeads | Mapping[str, str],
    expected_generation: int | None,
    *,
    operation_id: str | None = None,
    store: ArchitectureReviewStore | None = None,
) -> PromotionJournal:
    """Reserve a lineage generation and journal exact promotion revisions."""

    return (store or ArchitectureReviewStore(project)).reserve_promotion(
        unit_id,
        expected_heads,
        expected_generation,
        operation_id=operation_id,
    )


def promote_or_resume(
    project: ProjectContext,
    operation_id: str,
    *,
    store: ArchitectureReviewStore | None = None,
) -> PromotionJournal:
    """Promote or recover only the missing side of a durable journal."""

    return (store or ArchitectureReviewStore(project)).promote_or_resume(operation_id)


def stage_architecture_proposal(
    project: ProjectContext,
    *,
    owner: str,
    work_id: str,
    proposal: ArchitectureReviewUnit,
    expected_generation: int | None,
    store: ArchitectureReviewStore | None = None,
    renderer: C4ArtifactRenderer | None = None,
    render_settings: C4RenderSettings | None = None,
    baseline_artifact: C4SemanticModelArtifact | None = None,
    lineage_revision: str | None = None,
    plan_work_id: str | None = None,
) -> ArchitectureProposalState:
    """Stage committed proposal bytes after validating their pinned C4 evidence."""

    _authorize(proposal, owner, work_id)
    if proposal.status not in {"draft", "staged"}:
        raise ArchitectureProposalError(
            "review_required", "only a draft proposal can be staged"
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
    review_store = store or ArchitectureReviewStore(project)
    current = review_store.resolve_current(
        proposal.integration_lineage, lineage_revision=lineage_revision
    )
    generation = current.generation if current else None
    if generation != expected_generation:
        raise ArchitectureProposalError(
            "stale_baseline", "accepted architecture baseline generation changed"
        )
    staged = replace(proposal, status="staged")
    if review_store.baseline_status(staged, lineage_revision=lineage_revision).stale:
        raise ArchitectureProposalError(
            "stale_baseline", "proposal is not based on the current accepted architecture"
        )
    _validate_store_inputs(
        review_store,
        staged,
        lineage_revision=lineage_revision,
        plan_work_id=plan_work_id,
    )
    semantic_diff = _validate_proposed_model(
        project,
        staged,
        renderer=renderer,
        settings=render_settings,
        baseline_artifact=baseline_artifact,
    )
    review_store.save_staged(staged, semantic_diff)
    return ArchitectureProposalState(staged, current, None, semantic_diff)


def rebase_architecture_proposal(
    project: ProjectContext,
    *,
    owner: str,
    work_id: str,
    proposal: ArchitectureReviewUnit,
    store: ArchitectureReviewStore | None = None,
    renderer: C4ArtifactRenderer | None = None,
    render_settings: C4RenderSettings | None = None,
    baseline_artifact: C4SemanticModelArtifact | None = None,
    lineage_revision: str | None = None,
) -> ArchitectureProposalState:
    """Stage a changed proposal on the latest accepted integration lineage.

    The previous proposal remains in the review ledger (including its review and
    invalidation evidence).  The replacement receives a new tuple identity and
    starts at ``staged``, so an earlier review or approval cannot authorize the
    changed work.
    """

    _authorize(proposal, owner, work_id)
    review_store = store or ArchitectureReviewStore(project)
    previous = review_store.find_for_owner(owner, work_id, proposal.integration_lineage)
    current = review_store.resolve_current(
        proposal.integration_lineage, lineage_revision=lineage_revision
    )
    if current is None:
        raise ArchitectureProposalError(
            "stale_baseline", "no accepted architecture exists on the integration lineage"
        )

    if previous is not None:
        status = review_store.baseline_status(
            previous, lineage_revision=lineage_revision
        )
        if (
            status.stale
            and previous.review_unit_id != current.accepted_review_unit_id
            and previous.status not in {"stale", "rejected"}
        ):
            review_store.mark_stale(previous.review_unit_id, "stale_baseline")

    rebased = replace(
        proposal,
        proposed_ancestor_context=ProposedAncestorContext(
            previous.review_unit_id if previous is not None else current.accepted_review_unit_id,
            current.pointer_id,
            current.generation,
        ),
        accepted_baseline=current.baseline,
        baseline_pointer_id=current.pointer_id,
        baseline_generation=current.generation,
        status="draft",
    )
    if previous is not None and rebased.reviewed_tuple_digest == previous.reviewed_tuple_digest:
        raise ArchitectureProposalError(
            "review_required", "a revision must change the reviewable proposal tuple"
        )
    return stage_architecture_proposal(
        project,
        owner=owner,
        work_id=work_id,
        proposal=rebased,
        expected_generation=current.generation,
        store=review_store,
        renderer=renderer,
        render_settings=render_settings,
        baseline_artifact=baseline_artifact,
        lineage_revision=lineage_revision,
    )


def review_architecture_proposal(
    project: ProjectContext,
    *,
    owner: str,
    unit_id: str,
    expected_tuple_digest: str,
    decision: ReviewDecision,
    store: ArchitectureReviewStore | None = None,
    renderer: C4ArtifactRenderer | None = None,
    render_settings: C4RenderSettings | None = None,
    baseline_artifact: C4SemanticModelArtifact | None = None,
    reviewed_at: str | None = None,
    lineage_revision: str | None = None,
) -> ArchitectureProposalState:
    """Review the exact staged tuple; this operation never advances acceptance."""

    review_store = store or ArchitectureReviewStore(project)
    unit = review_store.get(unit_id)
    if unit is None:
        raise ArchitectureProposalError("review_required", "unknown architecture review unit")
    _authorize(unit, owner, unit.owner_work_id)
    if unit.status != "staged":
        raise ArchitectureProposalError(
            "review_required", "architecture review unit is not staged"
        )
    if expected_tuple_digest != unit.reviewed_tuple_digest:
        raise ArchitectureProposalError(
            "artifact_changed", "review tuple digest does not match the staged proposal"
        )
    if decision not in {"reviewed", "rejected"}:
        raise ArchitectureProposalError("review_required", "invalid review decision")
    if review_store.baseline_status(unit, lineage_revision=lineage_revision).stale:
        review_store.mark_stale(unit_id, "stale_baseline")
        raise ArchitectureProposalError(
            "stale_baseline", "proposal is not based on the current accepted architecture"
        )
    try:
        _validate_store_inputs(review_store, unit, lineage_revision=lineage_revision)
        semantic_diff = _validate_proposed_model(
            project,
            unit,
            renderer=renderer,
            settings=render_settings,
            baseline_artifact=baseline_artifact,
        )
    except ArchitectureProposalError as exc:
        reason = exc.code if exc.code in {"artifact_changed", "destination_changed"} else "artifact_changed"
        review_store.mark_stale(unit_id, reason)
        raise
    durable_diff = review_store.get_diff(unit_id)
    if durable_diff != semantic_diff:
        review_store.mark_stale(unit_id, "artifact_changed")
        raise ArchitectureProposalError(
            "artifact_changed", "validated semantic diff no longer matches the staged proposal"
        )
    timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()
    reviewed = review_store.record_review(
        unit_id, reviewer=owner, decision=decision, reviewed_at=timestamp
    )
    current = review_store.resolve_current(
        unit.integration_lineage, lineage_revision=lineage_revision
    )
    return ArchitectureProposalState(
        reviewed, current, review_store.get_review(unit_id), semantic_diff,
        review_store.get_invalidation_reasons(unit_id),
    )


def enable_review_gate(
    project: ProjectContext,
    *,
    version: int,
    store: ArchitectureReviewStore | None = None,
) -> None:
    """Explicitly enable a named architecture lifecycle policy version."""

    (store or ArchitectureReviewStore(project)).enable_gate_rollout(version)


def validate_review_gate(
    project: ProjectContext,
    *,
    work_id: str,
    boundary: ReviewGateBoundary,
    store: ArchitectureReviewStore | None = None,
    lineage_revision: str | None = None,
    blocking_work_ids: Sequence[str] = (),
    semantic_blockers: Sequence[BlockingScope] = (),
    approval_context: ReviewApprovalContext | None = None,
) -> ReviewGateResult:
    """Apply one revision-bound policy at every safe lifecycle boundary.

    Approval is the existing human boundary: it promotes an exact reviewed tuple
    to ``approved``.  Dispatch binds new work to the active rollout.  Work first
    observed later in its lifecycle is durably grandfathered at policy zero.
    """

    _nonblank(work_id, "review gate work ID")
    if boundary not in _REVIEW_GATE_BOUNDARIES:
        raise WorkspaceError("invalid architecture review gate boundary")
    review_store = store or ArchitectureReviewStore(project)
    active = review_store.gate_rollout_version()
    policy = review_store.gate_policy_version(work_id)
    hold = review_store.acceptance_hold(work_id)
    if hold is not None:
        raise ArchitectureProposalError(
            "acceptance_pending",
            f"promotion {hold} has not accepted both code and documentation",
        )
    if semantic_blockers:
        details = "; ".join(
            f"{item.thread_id} affected={','.join(item.affected_work_ids)} "
            f"reason={item.reason} fallback={str(item.fallback).lower()}"
            for item in semantic_blockers
        )
        raise ArchitectureProposalError(
            "review_required",
            "open semantic blocking review threads: " + details,
        )
    if active is None and policy is None:
        for unit in review_store.units_affecting(work_id):
            _validate_claimed_model(project, unit)
        return ReviewGateResult(
            work_id, boundary, _REVIEW_GATE_NAME, 0, None, None
        )
    if policy is None and boundary != "approval":
        policy = review_store.bind_gate_policy(
            work_id, active if boundary == "dispatch" else 0
        )
    blockers = tuple(dict.fromkeys(item for item in blocking_work_ids if item.strip()))
    if blockers:
        raise ArchitectureProposalError(
            "review_required",
            "open blocking review threads affect: " + ", ".join(blockers),
        )

    effective_policy = policy
    if effective_policy is None:
        effective_policy = active if boundary in {"approval", "dispatch"} else 0
    elif boundary == "approval" and active is not None and effective_policy < active:
        # A fresh approval is the explicit signal that a proposal was materially
        # revised; already executing work never reaches this path implicitly.
        effective_policy = active

    if effective_policy == 0:
        # A rollout exception never legalizes a claimed diagram without a model.
        for unit in review_store.units_affecting(work_id):
            _validate_claimed_model(project, unit)
        if policy is None:
            review_store.bind_gate_policy(work_id, 0)
        return ReviewGateResult(
            work_id, boundary, _REVIEW_GATE_NAME, 0, None, None
        )
    refreshed = resolve_review_gate_unit(
        review_store,
        work_id=work_id,
        policy=effective_policy,
        lineage_revision=lineage_revision,
        approval_context=approval_context if boundary == "approval" else None,
    )
    if refreshed.status == "stale":
        reasons = review_store.get_invalidation_reasons(refreshed.review_unit_id)
        code = reasons[-1] if reasons else "artifact_changed"
        raise ArchitectureProposalError(code, "approved architecture review tuple is stale")
    _validate_claimed_model(project, refreshed)
    if policy is None:
        policy = review_store.bind_gate_policy(work_id, effective_policy)
    elif policy != effective_policy:
        policy = review_store.rebind_gate_policy(work_id, effective_policy)
    if boundary == "approval":
        refreshed = review_store.approve_review_unit(refreshed.review_unit_id)
    elif refreshed.status != "approved":
        raise ArchitectureProposalError(
            "review_required", "architecture proposal is not approved for this boundary"
        )
    return ReviewGateResult(
        work_id,
        boundary,
        _REVIEW_GATE_NAME,
        policy,
        refreshed.review_unit_id,
        refreshed.reviewed_tuple_digest,
    )


def resolve_review_gate_unit(
    store: ArchitectureReviewStore,
    *,
    work_id: str,
    policy: int,
    lineage_revision: str | None = None,
    approval_context: ReviewApprovalContext | None = None,
) -> ArchitectureReviewUnit:
    """Resolve the same current affected tuple for every lifecycle boundary."""

    candidates = tuple(
        unit for unit in store.units_affecting(work_id)
        if unit.rollout_version == policy
    )
    if not candidates:
        raise ArchitectureProposalError(
            "review_required",
            f"work is bound to architecture review rollout v{policy} but has no proposal",
        )
    authoritative = candidates[-1]
    if approval_context is not None:
        actual = ReviewApprovalContext(
            authoritative.owner_work_id,
            authoritative.target_repository_key,
            authoritative.plan.revision,
            authoritative.review_unit_id,
            authoritative.reviewed_tuple_digest,
            authoritative.baseline_generation,
        )
        if approval_context != actual:
            raise ArchitectureProposalError(
                "stale_review_context",
                "displayed architecture review tuple is no longer authoritative",
            )
    return store.refresh(
        authoritative.review_unit_id,
        lineage_revision=lineage_revision,
    )


def _validate_claimed_model(
    project: ProjectContext, unit: ArchitectureReviewUnit
) -> None:
    if unit.architecture_impact == "diagram_change" and unit.proposed_model is None:
        raise ArchitectureProposalError(
            "model_required", "a diagram change requires a pinned model closure"
        )
    if unit.proposed_model is not None:
        _validate_model_binding(project, unit.proposed_model)


def _authorize(unit: ArchitectureReviewUnit, owner: str, work_id: str) -> None:
    if unit.authorized_owner != owner or unit.owner_work_id != work_id:
        raise ArchitectureProposalError(
            "owner_denied", "architecture proposal is outside the caller's owner scope"
        )


def _validate_store_inputs(
    store: ArchitectureReviewStore,
    unit: ArchitectureReviewUnit,
    *,
    lineage_revision: str | None = None,
    plan_work_id: str | None = None,
) -> None:
    try:
        store._validate_unit_inputs(unit)
        _validate_current_artifacts(
            store.project,
            unit,
            lineage_revision=lineage_revision,
            plan_work_id=plan_work_id,
        )
    except WorkspaceError as exc:
        detail = str(exc)
        code = "destination_changed" if "destination" in detail else "artifact_changed"
        raise ArchitectureProposalError(code, detail) from exc


def _refresh_review_unit(
    store: ArchitectureReviewStore,
    unit: ArchitectureReviewUnit,
    *,
    lineage_revision: str | None,
) -> ArchitectureReviewUnit:
    """Persist the first freshness failure; a later recheck never restores review."""

    if unit.status in {"stale", "rejected"}:
        return unit
    try:
        _validate_store_inputs(store, unit, lineage_revision=lineage_revision)
    except ArchitectureProposalError as exc:
        return store.mark_stale(unit.review_unit_id, exc.code)
    current = store.resolve_current(
        unit.integration_lineage, lineage_revision=lineage_revision
    )
    if (
        current is not None
        and current.accepted_review_unit_id == unit.review_unit_id
        and current.accepted_tuple_digest == unit.reviewed_tuple_digest
    ):
        # Acceptance advances the lineage from the unit's recorded baseline.
        # The accepted unit is therefore fresh against the pointer it created,
        # even though its input baseline IDs necessarily name the predecessor.
        return unit
    if store.baseline_status(unit, lineage_revision=lineage_revision).stale:
        return store.mark_stale(unit.review_unit_id, "stale_baseline")
    return unit


def _validate_proposed_model(
    project: ProjectContext,
    unit: ArchitectureReviewUnit,
    *,
    renderer: C4ArtifactRenderer | None,
    settings: C4RenderSettings | None,
    baseline_artifact: C4SemanticModelArtifact | None,
) -> C4SemanticDiff:
    if unit.architecture_impact == "no_diagram_change":
        return C4SemanticDiff(
            "unchanged",
            unit.accepted_baseline.accepted_review_unit_id,
            None,
            f"plan:{unit.plan.revision}",
            (),
            (),
            (),
            (),
            "unchanged: proposal explicitly records no diagram change",
        )
    binding = unit.proposed_model
    if binding is None:
        raise ArchitectureProposalError(
            "model_required", "a diagram change requires a pinned model closure"
        )
    chosen_settings = settings or C4RenderSettings()
    closure, render = _validate_model_binding(
        project, binding, renderer=renderer, settings=chosen_settings
    )
    proposed = C4SemanticModelArtifact(unit.review_unit_id, render, closure.contract)
    current = _validated_baseline_artifact(unit, baseline_artifact)
    if unit.accepted_baseline.kind == "empty_baseline":
        current = C4SemanticModelArtifact(
            "empty_baseline",
            C4RenderArtifact(status="empty", closure_digest="empty_baseline"),
            closure.contract,
        )
    source_reference = render.source_diff_reference or f"revision:{closure.revision}"
    diff = compute_c4_semantic_diff(
        current, proposed, source_diff_reference=source_reference
    )
    if diff.state == "render_error":
        raise ArchitectureProposalError("model_invalid", diff.error or diff.summary)
    return diff


def _validate_model_binding(
    project: ProjectContext,
    binding: ArchitectureModelBinding,
    *,
    renderer: C4ArtifactRenderer | None = None,
    settings: C4RenderSettings | None = None,
) -> tuple[C4SourceClosure, C4RenderArtifact]:
    """Reproduce a pinned model binding without relying on cached review state."""

    try:
        chosen_settings = settings or C4RenderSettings(**dict(binding.renderer_settings))
    except (TypeError, ValueError) as exc:
        raise ArchitectureProposalError("model_invalid", str(exc)) from exc
    expected_settings = tuple(sorted(chosen_settings.cache_payload().items()))
    if binding.renderer_settings != expected_settings:
        raise ArchitectureProposalError(
            "model_invalid", "renderer settings do not match the pinned model binding"
        )
    if binding.render_identity is not None:
        expected_identity = render_identity(binding.source_closure_digest, chosen_settings)
        if binding.render_identity != expected_identity:
            raise ArchitectureProposalError(
                "model_invalid", "render identity does not match the pinned model binding"
            )
    chosen_renderer = renderer or C4ArtifactRenderer(
        project.target.root / ".cascade" / "c4-render-cache"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="cascade-review-source-") as directory:
            closure = materialize_c4_source_closure(
                project,
                binding.contract.reference,
                tuple(item.reference for item in binding.sources),
                Path(directory) / "source",
            )
            render = chosen_renderer.submit(closure, chosen_settings).wait(
                timeout=chosen_settings.timeout_seconds + 5
            )
    except (C4SourceError, OSError, ValueError, TimeoutError) as exc:
        raise ArchitectureProposalError("model_invalid", str(exc)) from exc
    _verify_render_binding(binding, closure, render)
    return closure, render


def _verify_render_binding(
    binding: ArchitectureModelBinding,
    closure: C4SourceClosure,
    render: C4RenderArtifact,
) -> None:
    if closure.digest != binding.source_closure_digest:
        raise ArchitectureProposalError(
            "model_invalid", "pinned source closure digest does not match validation"
        )
    if render.status != "ready":
        detail = render.failure.message if render.failure else f"render is {render.status}"
        raise ArchitectureProposalError("model_invalid", detail)
    if render.closure_digest != closure.digest or render.image_digest != binding.renderer_image_digest:
        raise ArchitectureProposalError(
            "model_invalid", "render provenance does not match the pinned model binding"
        )
    if render.semantic_workspace is None or not render.semantic_workspace.is_file():
        raise ArchitectureProposalError("model_invalid", "render has no semantic model artifact")
    digest = hashlib.sha256(render.semantic_workspace.read_bytes()).hexdigest()
    if digest != binding.semantic_artifact_digest or render.semantic_workspace_sha256 != digest:
        raise ArchitectureProposalError(
            "model_invalid", "semantic model digest does not match the pinned binding"
        )


def _validated_baseline_artifact(
    unit: ArchitectureReviewUnit,
    artifact: C4SemanticModelArtifact | None,
) -> C4SemanticModelArtifact | None:
    if unit.accepted_baseline.kind == "empty_baseline":
        return None
    binding = unit.accepted_baseline.model
    if binding is None or artifact is None:
        raise ArchitectureProposalError(
            "model_invalid", "accepted model baseline artifact is required for semantic diff"
        )
    render = artifact.render
    if (
        render.status != "ready"
        or render.semantic_workspace is None
        or not render.semantic_workspace.is_file()
        or hashlib.sha256(render.semantic_workspace.read_bytes()).hexdigest()
        != binding.semantic_artifact_digest
    ):
        raise ArchitectureProposalError(
            "model_invalid", "accepted model baseline artifact does not match its pointer"
        )
    return artifact


def _mapping(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise WorkspaceError("invalid architecture review persistence payload")
    return value


def _semantic_diff_from_dict(value: object) -> C4SemanticDiff:
    row = _mapping(
        value,
        {
            "state",
            "current_artifact_ref",
            "proposed_artifact_ref",
            "source_diff_reference",
            "identities",
            "containment",
            "views",
            "changed_view_keys",
            "summary",
            "error",
        },
    )
    try:
        return C4SemanticDiff(
            state=row["state"],
            current_artifact_ref=row["current_artifact_ref"],
            proposed_artifact_ref=row["proposed_artifact_ref"],
            source_diff_reference=row["source_diff_reference"],
            identities=tuple(
                C4IdentityChange(
                    **{**item, "changed_fields": tuple(item["changed_fields"])}
                )
                for item in row["identities"]
            ),
            containment=tuple(C4ContainmentChange(**item) for item in row["containment"]),
            views=tuple(
                C4ViewDiff(
                    **{
                        **item,
                        "current_elements": tuple(item["current_elements"]),
                        "proposed_elements": tuple(item["proposed_elements"]),
                        "current_relationships": tuple(item["current_relationships"]),
                        "proposed_relationships": tuple(item["proposed_relationships"]),
                        "changed_identities": tuple(item["changed_identities"]),
                    }
                )
                for item in row["views"]
            ),
            changed_view_keys=tuple(row["changed_view_keys"]),
            summary=row["summary"],
            error=row["error"],
        )
    except (KeyError, TypeError) as exc:
        raise WorkspaceError("invalid persisted architecture semantic diff") from exc


def _nonblank(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{field} must be non-blank")


def _role(value: object) -> None:
    if value not in {"target", "tracking"}:
        raise WorkspaceError("invalid repository role")


def _relative_path(path: Path, field: str, *, allow_root: bool = False) -> None:
    if path.is_absolute() or any(part in {"", ".."} for part in path.parts):
        raise WorkspaceError(f"{field} path must be repository-relative")
    if path == Path(".") and not allow_root:
        raise WorkspaceError(f"{field} path must not be the repository root")


def _portable_path(path: Path) -> str:
    return "." if path == Path(".") else path.as_posix()


def _stored_path(value: str, *, allow_root: bool = False) -> Path:
    path = Path(value)
    _relative_path(path, "stored", allow_root=allow_root)
    return path


def _revision(value: object, field: str) -> None:
    if not isinstance(value, str) or _REVISION.fullmatch(value) is None:
        raise WorkspaceError(f"invalid {field} revision")


def _digest(value: object, field: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise WorkspaceError(f"invalid {field} digest")


def _generation(value: object, field: str, *, allow_none: bool = True) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WorkspaceError(f"{field} must be a positive integer")


def _unique_nonblank(values: Sequence[str], field: str) -> None:
    if any(not value.strip() for value in values) or len(values) != len(set(values)):
        raise WorkspaceError(f"{field} must be unique and non-blank")


def _json_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _verify_digest(content: bytes, expected: str) -> None:
    if expected.removeprefix("sha256:") != hashlib.sha256(content).hexdigest():
        raise WorkspaceError("pinned artifact content digest does not match committed bytes")


def _repository(project: ProjectContext, role: str, key: str) -> RepositoryContext:
    repository = project.target if role == "target" else project.tracking
    if key != repository.repository_key:
        raise WorkspaceError("pinned repository identity has changed")
    return repository


def _architecture_repository(
    project: ProjectContext, role: str, key: str
) -> RepositoryContext:
    repository = project.target if role == "target" else project.tracking
    expected = (
        project.target_repository_key if role == "target" else repository.repository_key
    )
    if key != expected:
        raise WorkspaceError("pinned architecture repository identity has changed")
    return repository


def _git_blob(repository: RepositoryContext, revision: str, path: Path, field: str) -> bytes:
    result = subprocess.run(["git", "show", f"{revision}:{path.as_posix()}"], cwd=repository.root,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if result.returncode != 0:
        raise WorkspaceError(f"cannot read pinned {field} at its recorded revision")
    return result.stdout


def _read_pinned_document(project: ProjectContext, reference: PinnedDocumentRef) -> bytes:
    return _git_blob(_repository(project, reference.repository_role, reference.repository_key),
                     reference.revision, reference.path, "review plan")


def _read_architecture_bytes(project: ProjectContext, reference: ArchitectureArtifactRef) -> bytes:
    if reference.target_repository_key != project.target_repository_key:
        raise WorkspaceError("architecture artifact belongs to another target")
    repository = _architecture_repository(
        project,
        reference.destination_repository_role,
        reference.destination_repository_key,
    )
    return _git_blob(repository, reference.revision, reference.repository_path,
                     "architecture artifact")


def _validate_current_artifacts(
    project: ProjectContext,
    unit: ArchitectureReviewUnit,
    *,
    lineage_revision: str | None,
    plan_work_id: str | None = None,
) -> None:
    """Ensure every reviewed path still has its pinned bytes at the active heads."""

    plan_repository = _repository(
        project, unit.plan.repository_role, unit.plan.repository_key
    )
    registered_plan = _registered_owner_checkout(
        plan_repository, plan_work_id or unit.owner_work_id
    )
    if registered_plan is not None:
        plan_head, plan_checkout = registered_plan
    else:
        plan_head = (
            lineage_revision
            if lineage_revision is not None and unit.plan.repository_role == "target"
            else _head(plan_repository.root)
        )
        plan_checkout = plan_repository.root
    _verify_current_blob(
        plan_repository, unit.plan.revision, plan_head, unit.plan.path,
        unit.plan.content_digest, "review plan", checkout=plan_checkout,
    )

    artifacts = [unit.design]
    if unit.proposed_model:
        artifacts.extend((unit.proposed_model.contract, *unit.proposed_model.sources))
    for artifact in artifacts:
        reference = artifact.reference
        repository = _architecture_repository(
            project,
            reference.destination_repository_role,
            reference.destination_repository_key,
        )
        registered_artifact = _registered_owner_checkout(
            repository, reference.owning_work
        )
        if registered_artifact is not None:
            current_head, checkout = registered_artifact
        else:
            current_head = (
                lineage_revision
                if lineage_revision is not None and reference.destination_repository_role == "target"
                else _head(repository.root)
            )
            checkout = repository.root
        _verify_current_blob(
            repository, reference.revision, current_head, reference.repository_path,
            artifact.content_digest, "architecture artifact", checkout=checkout,
        )


def _verify_current_blob(
    repository: RepositoryContext,
    pinned_revision: str,
    current_revision: str,
    path: Path,
    content_digest: str,
    field: str,
    *,
    checkout: Path,
) -> None:
    _require_commit(repository.root, current_revision, f"current {field}")
    if not _is_ancestor(repository.root, pinned_revision, current_revision):
        raise WorkspaceError(f"pinned {field} revision is not in the current lineage")
    changed = subprocess.run(
        ["git", "log", "--format=%H", f"{pinned_revision}..{current_revision}", "--",
         path.as_posix()],
        cwd=repository.root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if changed.returncode != 0:
        raise WorkspaceError(f"cannot inspect current {field} history")
    if changed.stdout.strip():
        raise WorkspaceError(f"pinned {field} changed after its recorded revision")
    _verify_digest(
        _git_blob(repository, current_revision, path, f"current {field}"),
        content_digest,
    )
    # When the active lineage is this checkout's HEAD, its working bytes are
    # also reviewable state.  This mirrors Feature A's pinning rule and catches
    # an edit or deletion before it is committed.  A caller validating another
    # lineage revision must only inspect that commit, not an unrelated checkout.
    if current_revision == _head(checkout):
        try:
            working_bytes = (checkout / path).read_bytes()
        except OSError as exc:
            raise WorkspaceError(f"current {field} working bytes are not readable") from exc
        _verify_digest(working_bytes, content_digest)


def resolve_registered_owner_revision(
    repository: RepositoryContext, work_id: str
) -> str:
    """Return the committed head for one registered owner, or repository trunk."""

    return _registered_owner_head(repository, work_id)[0]


def _registered_owner_head(
    repository: RepositoryContext, work_id: str
) -> tuple[str, Path]:
    """Resolve only a canonical registered checkout owned by ``work_id``."""

    registered = _registered_owner_checkout(repository, work_id)
    if registered is not None:
        return registered
    return _head(repository.root), repository.root


def _registered_owner_checkout(
    repository: RepositoryContext, work_id: str
) -> tuple[str, Path] | None:
    """Return the validated owner checkout without substituting repository HEAD."""

    trunk = locate_trunk(repository.root).resolve()
    matches = [
        entry for entry in load_registry_readonly(trunk)
        if entry.work_id == work_id
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise WorkspaceError(f"multiple registered lineages own {work_id}")
    entry = matches[0]
    expected_branch = integration_branch(entry.kind, work_id)
    expected_path = integration_worktree_path(entry.kind, work_id, trunk=trunk)
    if entry.branch != expected_branch or entry.path.resolve() != expected_path:
        raise WorkspaceError(f"registered lineage ownership changed for {work_id}")
    if not entry.path.is_dir():
        raise WorkspaceError(f"registered lineage checkout is missing for {work_id}")
    branch = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=entry.path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if branch.returncode != 0 or branch.stdout.strip() != entry.branch:
        raise WorkspaceError(f"registered lineage branch changed for {work_id}")
    return _head(entry.path), entry.path


def _head(repository: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD^{commit}"], cwd=repository, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    revision = result.stdout.strip()
    if result.returncode != 0 or _REVISION.fullmatch(revision) is None:
        raise WorkspaceError("cannot resolve integration lineage revision")
    return revision


def _require_commit(repository: Path, revision: str, field: str) -> None:
    _revision(revision, field)
    result = subprocess.run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=repository,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode != 0:
        raise WorkspaceError(f"{field} revision is unavailable")


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                            cwd=repository, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False)
    if result.returncode not in {0, 1}:
        raise WorkspaceError("cannot resolve accepted architecture lineage ancestry")
    return result.returncode == 0


def _merge_promotion_commits(repository: Path, revisions: Sequence[str]) -> bool:
    """Merge exact commits, leaving the checkout clean when Git reports a conflict."""

    in_progress = subprocess.run(
        ["git", "rev-parse", "--verify", "MERGE_HEAD"], cwd=repository,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    unmerged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"], cwd=repository, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    if in_progress.returncode == 0 or unmerged.returncode != 0 or unmerged.stdout.strip():
        return False
    result = subprocess.run(
        ["git", "merge", "--no-edit", "--no-ff", *revisions], cwd=repository,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode == 0:
        return True
    subprocess.run(
        ["git", "merge", "--abort"], cwd=repository,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return False


def _promotion_heads(value: PromotionHeads | Mapping[str, str]) -> PromotionHeads:
    if isinstance(value, PromotionHeads):
        return value
    if not isinstance(value, Mapping):
        raise WorkspaceError("invalid promotion heads")
    return PromotionHeads.from_dict(dict(value))


def _new_promotion_journal(
    operation_id: str,
    unit: ArchitectureReviewUnit,
    heads: PromotionHeads,
    generation: int | None,
) -> PromotionJournal:
    return PromotionJournal(
        operation_id=operation_id,
        lineage_key=unit.integration_lineage,
        reserved_generation=generation,
        approved_review_unit_id=unit.review_unit_id,
        approved_tuple_digest=unit.reviewed_tuple_digest,
        code_repository_key=unit.code_repository_key,
        documentation_repository_key=unit.documentation_repository_key,
        documentation_repository_role=unit.documentation_repository_role,
        documentation_destination_path=unit.documentation_destination_path,
        heads=heads,
        code=PromotionSide(),
        documentation=PromotionSide(),
        outcome="reserved",
    )


def _same_promotion_identity(left: PromotionJournal, right: PromotionJournal) -> bool:
    """Ignore only result fields when recognizing an idempotent reservation retry."""

    return (
        left.operation_id == right.operation_id
        and left.lineage_key == right.lineage_key
        and left.reserved_generation == right.reserved_generation
        and left.approved_review_unit_id == right.approved_review_unit_id
        and left.approved_tuple_digest == right.approved_tuple_digest
        and left.code_repository_key == right.code_repository_key
        and left.documentation_repository_key == right.documentation_repository_key
        and left.documentation_repository_role == right.documentation_repository_role
        and left.documentation_destination_path == right.documentation_destination_path
        and left.heads == right.heads
    )


__all__ = ["AcceptedArchitecturePointer", "AcceptedLineage", "ArchitectureBaseline",
           "ArchitectureModelBinding", "ArchitectureProposalError",
           "ArchitectureProposalState", "ArchitectureReviewRecord",
           "ArchitectureReviewStore", "ArchitectureReviewUnit",
           "PinnedArchitectureArtifact", "PinnedDocumentRef", "ProposedAncestorContext",
           "PromotionHeads", "PromotionJournal", "PromotionSide",
           "ReviewBaselineStatus", "ReviewGateBoundary", "ReviewGateResult",
           "enable_review_gate", "read_architecture_state",
           "promote_or_resume", "rebase_architecture_proposal", "reserve_promotion",
           "review_architecture_proposal", "stage_architecture_proposal",
           "validate_review_gate"]
