"""Verified documentation context for semantic C4 selections.

The resolver in this module is deliberately I/O free.  Callers load a small,
versioned mapping from an already-authorized review unit or browsing snapshot
and pass only its pinned descriptors here.  Full document bytes remain lazy
resources owned by the HTTP layer.

No field containing display text participates in matching.  Coverage exists
only when an explicit association names the selection's stable semantic ID.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Hashable, Iterable, Literal, Mapping, Sequence

from cascade.workspace.architecture_review import ArchitectureReviewUnit
from cascade.workspace.errors import WorkspaceError


SelectionKind = Literal["view", "element", "relationship"]
DocumentKind = Literal["requirement", "decision"]
ReferenceState = Literal["available", "missing", "stale"]
AssociationProvenance = Literal["explicit_mapping", "reviewed_association"]
ScopeKind = Literal["review", "snapshot"]

MAX_CONTEXT_DOCUMENTS = 256
MAX_CONTEXT_ASSOCIATIONS = 512
MAX_CONTEXT_DESIGNS = 128

_REVISION = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class PinnedContextRevision:
    """One repository revision authorized by the selected review/snapshot."""

    repository_key: str
    revision: str

    def __post_init__(self) -> None:
        _nonblank(self.repository_key, "repository key")
        _revision(self.revision)


@dataclass(frozen=True)
class PinnedSourceSection:
    """A source location; ``section`` is required for requirement/decision links."""

    repository_key: str
    revision: str
    path: Path
    section: str | None = None
    content_digest: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.repository_key, "source repository key")
        _revision(self.revision)
        _relative_path(self.path, "source path")
        if self.section is not None:
            _nonblank(self.section, "source section")
        if self.content_digest is not None and _DIGEST.fullmatch(self.content_digest) is None:
            raise WorkspaceError("source content digest must be a SHA-256 digest")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "repository_key": self.repository_key,
            "revision": self.revision,
            "path": self.path.as_posix(),
            "section": self.section,
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class ContextDocument:
    """A stable requirement or decision and its explicitly recorded source."""

    document_id: str
    kind: DocumentKind
    title: str
    source: PinnedSourceSection | None
    state: ReferenceState = "available"
    reason: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.document_id, "document ID")
        if self.kind not in {"requirement", "decision"}:
            raise WorkspaceError("invalid context document kind")
        _nonblank(self.title, "document title")
        if self.state not in {"available", "missing", "stale"}:
            raise WorkspaceError("invalid context document state")
        if self.state != "missing" and self.source is None:
            raise WorkspaceError("available and stale documents require a pinned source")
        if self.source is not None and self.source.section is None:
            raise WorkspaceError("context documents require an explicit source section")
        if self.state != "available" and not (self.reason and self.reason.strip()):
            raise WorkspaceError("missing and stale documents require a reason")


@dataclass(frozen=True)
class C4ContextAssociation:
    """One explicit edge between a semantic target and a stable document ID."""

    selection_kind: SelectionKind
    semantic_id: str
    document_id: str
    document_kind: DocumentKind
    provenance: AssociationProvenance
    evidence_id: str
    view_key: str | None = None
    level: str | None = None

    def __post_init__(self) -> None:
        if self.selection_kind not in {"view", "element", "relationship"}:
            raise WorkspaceError("invalid C4 context association kind")
        _nonblank(self.semantic_id, "semantic ID")
        _nonblank(self.document_id, "document ID")
        if self.document_kind not in {"requirement", "decision"}:
            raise WorkspaceError("invalid associated document kind")
        if self.provenance not in {"explicit_mapping", "reviewed_association"}:
            raise WorkspaceError("invalid context association provenance")
        _nonblank(self.evidence_id, "association evidence ID")
        if self.view_key is not None:
            _nonblank(self.view_key, "association view key")
        if self.level is not None:
            _nonblank(self.level, "association view level")


@dataclass(frozen=True)
class C4ContextSelection:
    kind: SelectionKind
    semantic_id: str
    view_key: str | None = None
    level: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"view", "element", "relationship"}:
            raise WorkspaceError("invalid C4 context selection kind")
        _nonblank(self.semantic_id, "semantic ID")
        if self.view_key is not None:
            _nonblank(self.view_key, "selection view key")
        if self.level is not None:
            _nonblank(self.level, "selection view level")


@dataclass(frozen=True)
class DesignContext:
    """A design offered as ownership context, never as claimed target coverage."""

    code_directory: Path
    design_owner_directory: Path
    source: PinnedSourceSection
    state: ReferenceState = "available"
    reason: str | None = None

    def __post_init__(self) -> None:
        _relative_path(self.code_directory, "code directory", allow_root=True)
        _relative_path(self.design_owner_directory, "design owner directory", allow_root=True)
        if self.state not in {"available", "missing", "stale"}:
            raise WorkspaceError("invalid design context state")
        if self.state != "available" and not (self.reason and self.reason.strip()):
            raise WorkspaceError("missing and stale design context requires a reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "code_directory": _portable(self.code_directory),
            "design_owner_directory": _portable(self.design_owner_directory),
            "source": self.source.to_dict(),
            "state": self.state,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class C4DocumentationEvidence:
    """Bounded, pinned inputs for a review unit or branch snapshot."""

    scope_kind: ScopeKind
    scope_id: str
    pinned_revisions: tuple[PinnedContextRevision, ...]
    documents: tuple[ContextDocument, ...]
    associations: tuple[C4ContextAssociation, ...]
    owner_context: tuple[DesignContext, ...] = ()
    broader_index: tuple[DesignContext, ...] = ()
    mapping_source: PinnedSourceSection | None = None
    documentation_association: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.scope_kind not in {"review", "snapshot"}:
            raise WorkspaceError("invalid documentation context scope")
        _nonblank(self.scope_id, "context scope ID")
        if not self.pinned_revisions:
            raise WorkspaceError("documentation context requires pinned revisions")
        _bounded(self.documents, MAX_CONTEXT_DOCUMENTS, "context documents")
        _bounded(self.associations, MAX_CONTEXT_ASSOCIATIONS, "context associations")
        _bounded(self.owner_context, MAX_CONTEXT_DESIGNS, "owner design context")
        _bounded(self.broader_index, MAX_CONTEXT_DESIGNS, "broader design index")
        _unique(
            ((row.repository_key, row.revision) for row in self.pinned_revisions),
            "pinned context revisions",
        )
        _unique((row.document_id for row in self.documents), "context document IDs")
        _unique(self.associations, "context associations")
        if self.mapping_source is not None and (
            self.mapping_source.repository_key,
            self.mapping_source.revision,
        ) not in {
            (row.repository_key, row.revision) for row in self.pinned_revisions
        }:
            raise WorkspaceError("context mapping source is outside pinned revisions")
        _unique(
            (key for key, _value in self.documentation_association),
            "documentation association fields",
        )


@dataclass(frozen=True)
class ResolvedContextLink:
    document_id: str
    kind: DocumentKind
    title: str | None
    source: PinnedSourceSection | None
    state: ReferenceState
    reason: str | None
    provenance: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "kind": self.kind,
            "title": self.title,
            "source": self.source.to_dict() if self.source is not None else None,
            "state": self.state,
            "reason": self.reason,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class ResolvedC4DocumentationContext:
    scope_kind: ScopeKind
    scope_id: str
    selection: C4ContextSelection
    mapping_state: Literal["mapped", "unmapped"]
    explicit_target_links: tuple[ResolvedContextLink, ...]
    view_links: tuple[ResolvedContextLink, ...]
    owner_context: tuple[DesignContext, ...]
    broader_index: tuple[DesignContext, ...]
    pinned_revisions: tuple[PinnedContextRevision, ...]
    mapping_source: PinnedSourceSection | None
    documentation_association: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "scope_kind": self.scope_kind,
            "scope_id": self.scope_id,
            "selection": asdict(self.selection),
            "mapping_state": self.mapping_state,
            "explicit_target_links": [
                row.to_dict() for row in self.explicit_target_links
            ],
            "view_links": [row.to_dict() for row in self.view_links],
            "owner_context": [row.to_dict() for row in self.owner_context],
            "broader_index": [row.to_dict() for row in self.broader_index],
            "pinned_revisions": [asdict(row) for row in self.pinned_revisions],
            "mapping_source": (
                self.mapping_source.to_dict()
                if self.mapping_source is not None else None
            ),
            "documentation_association": dict(self.documentation_association),
        }

    @property
    def explicit_links(self) -> tuple[ResolvedContextLink, ...]:
        """Compatibility alias for the now-unambiguous target collection."""

        return self.explicit_target_links


def resolve_c4_documentation_context(
    evidence: C4DocumentationEvidence,
    selection: C4ContextSelection,
) -> ResolvedC4DocumentationContext:
    """Resolve exact edges without reading files or inferring semantic coverage."""

    documents = {row.document_id: row for row in evidence.documents}
    target_matching = [
        row for row in evidence.associations if _association_matches(row, selection)
    ]
    if selection.kind == "view":
        view_matching = target_matching
        target_matching = []
    elif selection.view_key is None:
        view_matching = []
    else:
        view_selection = C4ContextSelection(
            "view",
            selection.view_key,
            view_key=selection.view_key,
            level=selection.level,
        )
        view_matching = [
            row
            for row in evidence.associations
            if _association_matches(row, view_selection)
        ]

    explicit_links = _resolve_links(
        target_matching, documents, evidence.pinned_revisions
    )
    view_links = _resolve_links(view_matching, documents, evidence.pinned_revisions)

    pinned = {
        (row.repository_key, row.revision) for row in evidence.pinned_revisions
    }
    owner = tuple(_pin_design(row, pinned) for row in evidence.owner_context)
    broader = tuple(_pin_design(row, pinned) for row in evidence.broader_index)
    selected_links = view_links if selection.kind == "view" else explicit_links
    return ResolvedC4DocumentationContext(
        evidence.scope_kind,
        evidence.scope_id,
        selection,
        "mapped" if selected_links else "unmapped",
        explicit_links,
        view_links,
        owner,
        broader,
        evidence.pinned_revisions,
        evidence.mapping_source,
        evidence.documentation_association,
    )


def _resolve_links(
    matching: Sequence[C4ContextAssociation],
    documents: Mapping[str, ContextDocument],
    revisions: Sequence[PinnedContextRevision],
) -> tuple[ResolvedContextLink, ...]:
    """Resolve one relationship class without blending its coverage semantics."""

    by_document: dict[tuple[str, DocumentKind], list[C4ContextAssociation]] = {}
    for row in matching:
        by_document.setdefault((row.document_id, row.document_kind), []).append(row)

    pinned = {
        (row.repository_key, row.revision) for row in revisions
    }
    links: list[ResolvedContextLink] = []
    for (document_id, kind), rows in sorted(by_document.items()):
        document = documents.get(document_id)
        provenance = tuple(
            {
                "relation": row.provenance,
                "evidence_id": row.evidence_id,
                "selection_kind": row.selection_kind,
                "semantic_id": row.semantic_id,
                **({"view_key": row.view_key} if row.view_key is not None else {}),
                **({"level": row.level} if row.level is not None else {}),
            }
            for row in sorted(rows, key=lambda item: (item.provenance, item.evidence_id))
        )
        if document is None or document.kind != kind:
            reason = "reference_missing" if document is None else "document_kind_mismatch"
            links.append(
                ResolvedContextLink(
                    document_id, kind, None, None, "missing", reason, provenance
                )
            )
            continue
        state, reason = _reference_state(document.state, document.reason, document.source, pinned)
        links.append(
            ResolvedContextLink(
                document.document_id,
                document.kind,
                document.title,
                document.source,
                state,
                reason,
                provenance,
            )
        )

    return tuple(links)


def review_documentation_evidence(
    unit: ArchitectureReviewUnit,
    documents: Sequence[ContextDocument],
    *,
    associations: Sequence[C4ContextAssociation] = (),
    owner_context: Sequence[DesignContext] = (),
    broader_index: Sequence[DesignContext] = (),
) -> C4DocumentationEvidence:
    """Build proposed-side evidence from an exact reviewed tuple.

    Review-unit citations are explicit only at their recorded view IDs.  They
    are not promoted to element or relationship coverage.  More specific
    reviewed mappings can be supplied in ``associations``.
    """

    reviewed = tuple(
        C4ContextAssociation(
            "view",
            view_id,
            document_id,
            kind,
            "reviewed_association",
            unit.review_unit_id,
        )
        for view_id in unit.view_citations
        for kind, identifiers in (
            ("requirement", unit.requirement_citations),
            ("decision", unit.decision_citations),
        )
        for document_id in identifiers
    )
    design = unit.design
    default_owner = (
        DesignContext(
            unit.code_directory,
            unit.design_owner_directory,
            PinnedSourceSection(
                design.reference.destination_repository_key,
                design.reference.revision,
                design.reference.repository_path,
                content_digest=design.content_digest,
            ),
        ),
    )
    revisions = {
        (unit.plan.repository_key, unit.plan.revision),
        (
            design.reference.destination_repository_key,
            design.reference.revision,
        ),
    }
    return C4DocumentationEvidence(
        "review",
        unit.review_unit_id,
        tuple(PinnedContextRevision(*row) for row in sorted(revisions)),
        tuple(documents),
        (*reviewed, *tuple(associations)),
        tuple(owner_context) or default_owner,
        tuple(broader_index),
    )


def snapshot_documentation_evidence(
    snapshot_id: str,
    descriptor: dict[str, object],
    documents: Sequence[ContextDocument],
    associations: Sequence[C4ContextAssociation],
    *,
    owner_context: Sequence[DesignContext] = (),
    broader_index: Sequence[DesignContext] = (),
) -> C4DocumentationEvidence:
    """Bind context to the exact code/document pair in a snapshot descriptor."""

    try:
        repositories = descriptor["repositories"]
        revisions = descriptor["revisions"]
        if not isinstance(repositories, dict) or not isinstance(revisions, dict):
            raise TypeError
        pairs = {
            (repositories["code"], revisions["code"]),
            (repositories["documentation"], revisions["documentation"]),
        }
        if not all(isinstance(item, str) for pair in pairs for item in pair):
            raise TypeError
        mapping = descriptor["mapping"]
        if not isinstance(mapping, dict):
            raise TypeError
        mapping_source = PinnedSourceSection(
            mapping["repository_key"], mapping["revision"], Path(mapping["path"])
        )
        if (mapping_source.repository_key, mapping_source.revision) != (
            repositories["code"], revisions["code"]
        ):
            raise WorkspaceError(
                "architecture snapshot mapping is not pinned to the code revision"
            )
        association = descriptor["association"]
        if not isinstance(association, dict):
            raise TypeError
        provenance = association["provenance"]
        evidence_id = association.get("evidence_id")
        if not isinstance(provenance, str) or not provenance.strip():
            raise TypeError
        if evidence_id is not None and (
            not isinstance(evidence_id, str) or not evidence_id.strip()
        ):
            raise TypeError
        if repositories["code"] != repositories["documentation"] and evidence_id is None:
            raise WorkspaceError(
                "split architecture snapshot requires recorded association evidence"
            )
    except (KeyError, TypeError) as exc:
        raise WorkspaceError("invalid architecture snapshot provenance") from exc
    return C4DocumentationEvidence(
        "snapshot",
        snapshot_id,
        tuple(PinnedContextRevision(*row) for row in sorted(pairs)),
        tuple(documents),
        tuple(associations),
        tuple(owner_context),
        tuple(broader_index),
        mapping_source,
        tuple(
            (key, value) for key, value in (
                ("provenance", provenance),
                ("evidence_id", evidence_id),
            ) if value is not None
        ),
    )


def _association_matches(
    association: C4ContextAssociation, selection: C4ContextSelection
) -> bool:
    if (
        association.selection_kind != selection.kind
        or association.semantic_id != selection.semantic_id
    ):
        return False
    if association.view_key is not None and association.view_key != selection.view_key:
        return False
    if association.level is not None and association.level != selection.level:
        return False
    return True


def _reference_state(
    state: ReferenceState,
    reason: str | None,
    source: PinnedSourceSection | None,
    pinned: set[tuple[str, str]],
) -> tuple[ReferenceState, str | None]:
    if state == "missing":
        return state, reason
    assert source is not None
    if (source.repository_key, source.revision) not in pinned:
        return "stale", "revision_not_in_scope"
    return state, reason


def _pin_design(
    design: DesignContext, pinned: set[tuple[str, str]]
) -> DesignContext:
    state, reason = _reference_state(
        design.state, design.reason, design.source, pinned
    )
    return replace(design, state=state, reason=reason)


def _bounded(values: Sequence[object], maximum: int, field: str) -> None:
    if len(values) > maximum:
        raise WorkspaceError(f"{field} exceeds the bounded limit of {maximum}")


def _unique(values: Iterable[Hashable], field: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise WorkspaceError(f"{field} must be unique")


def _nonblank(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{field} must be non-blank")


def _revision(value: str) -> None:
    if not isinstance(value, str) or _REVISION.fullmatch(value) is None:
        raise WorkspaceError("context revision must be a full Git object ID")


def _relative_path(path: Path, field: str, *, allow_root: bool = False) -> None:
    pure = PurePosixPath(path.as_posix())
    if pure.is_absolute() or ".." in pure.parts or (not allow_root and pure == PurePosixPath(".")):
        raise WorkspaceError(f"{field} must be a confined relative path")


def _portable(path: Path) -> str:
    return "." if path == Path(".") else path.as_posix()


__all__ = [
    "MAX_CONTEXT_ASSOCIATIONS",
    "MAX_CONTEXT_DESIGNS",
    "MAX_CONTEXT_DOCUMENTS",
    "C4ContextAssociation",
    "C4ContextSelection",
    "C4DocumentationEvidence",
    "ContextDocument",
    "DesignContext",
    "PinnedContextRevision",
    "PinnedSourceSection",
    "ResolvedC4DocumentationContext",
    "ResolvedContextLink",
    "resolve_c4_documentation_context",
    "review_documentation_evidence",
    "snapshot_documentation_evidence",
]
