"""Durable, revision-bound architecture review units and lineage baselines."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from cascade.workspace.architecture import ArchitectureArtifactRef
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext, RepositoryContext

_SCHEMA_VERSION = 1
_REVISION = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
RepositoryRole = Literal["target", "tracking"]
ReviewStatus = Literal["draft", "staged", "reviewed", "approved", "stale", "rejected"]


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

    def __post_init__(self) -> None:
        if not self.sources:
            raise WorkspaceError("a diagram change requires a nonempty model closure")
        _digest(self.source_closure_digest, "model source closure")
        _digest(self.renderer_image_digest, "renderer image")
        _digest(self.semantic_artifact_digest, "semantic model artifact")
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
        return {"contract": self.contract.to_dict(),
                "sources": [item.to_dict() for item in self.sources],
                "source_closure_digest": self.source_closure_digest,
                "renderer_image_digest": self.renderer_image_digest,
                "renderer_settings": dict(self.renderer_settings),
                "semantic_artifact_digest": self.semantic_artifact_digest}

    @classmethod
    def from_dict(cls, value: object) -> "ArchitectureModelBinding":
        row = _mapping(value, {"contract", "sources", "source_closure_digest",
                               "renderer_image_digest", "renderer_settings",
                               "semantic_artifact_digest"})
        if not isinstance(row["sources"], list) or not isinstance(row["renderer_settings"], dict):
            raise WorkspaceError("invalid architecture model binding")
        if not all(isinstance(row[field], str) for field in
                   ("source_closure_digest", "renderer_image_digest", "semantic_artifact_digest")):
            raise WorkspaceError("invalid architecture model binding")
        return cls(PinnedArchitectureArtifact.from_dict(row["contract"]),
                   tuple(PinnedArchitectureArtifact.from_dict(item) for item in row["sources"]),
                   row["source_closure_digest"], row["renderer_image_digest"],
                   tuple(sorted(row["renderer_settings"].items())), row["semantic_artifact_digest"])


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
            raise WorkspaceError("a diagram change requires a pinned model closure")
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
        return f"architecture-review-{_json_digest(self.to_dict())}"

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
class ReviewBaselineStatus:
    current: AcceptedLineage | None
    stale: bool
    rebase_required: bool


class ArchitectureReviewStore:
    def __init__(self, project: ProjectContext, path: Path | None = None) -> None:
        self.project = project
        self.path = path or project.target.root / "architecture" / "review-units.json"

    def save(self, unit: ArchitectureReviewUnit) -> str:
        self._validate_unit_inputs(unit)
        state = self._read()
        identity, encoded = unit.review_unit_id, unit.to_dict()
        existing = state["review_units"].get(identity)
        if existing is not None and existing != encoded:
            raise WorkspaceError("architecture review unit identity collision")
        state["review_units"][identity] = encoded
        self._write(state)
        return identity

    def get(self, review_unit_id: str) -> ArchitectureReviewUnit | None:
        value = self._read()["review_units"].get(review_unit_id)
        return ArchitectureReviewUnit.from_dict(value) if value is not None else None

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
        unit = self.get(review_unit_id)
        if unit is None:
            raise WorkspaceError("unknown architecture review unit")
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
            return {"version": _SCHEMA_VERSION, "review_units": {}, "lineages": {}}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"invalid architecture review store: {self.path}") from exc
        if (not isinstance(state, dict) or set(state) != {"version", "review_units", "lineages"} or
                state["version"] != _SCHEMA_VERSION or not isinstance(state["review_units"], dict) or
                not isinstance(state["lineages"], dict)):
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


def _mapping(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise WorkspaceError("invalid architecture review persistence payload")
    return value


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


__all__ = ["AcceptedArchitecturePointer", "AcceptedLineage", "ArchitectureBaseline",
           "ArchitectureModelBinding", "ArchitectureReviewStore", "ArchitectureReviewUnit",
           "PinnedArchitectureArtifact", "PinnedDocumentRef", "ProposedAncestorContext",
           "ReviewBaselineStatus"]
