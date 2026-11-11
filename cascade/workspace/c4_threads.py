"""Semantic anchors stored on existing architecture review comment roots."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from cascade.comments.store import comment, read_comments
from cascade.workspace.c4_review import C4ReviewPayload, C4ReviewSide
from cascade.workspace.errors import WorkspaceError


AnchorKind = Literal["requirement", "view", "element", "relationship"]
AnchorSide = Literal["current", "proposed"]
AnchorFreshness = Literal["current", "outdated"]


@dataclass(frozen=True)
class SemanticThreadAnchor:
    """Immutable semantic identity and original review links for one thread."""

    version: int
    kind: AnchorKind
    target_key: str
    view_key: str | None
    level: str | None
    source_side: AnchorSide
    repository_key: str
    revision: str
    review_unit_id: str
    reviewed_tuple_digest: str
    original_source_reference: str
    original_diff_link: str

    def __post_init__(self) -> None:
        if self.version != 1:
            raise WorkspaceError("unsupported semantic thread anchor version")
        if self.kind not in {"requirement", "view", "element", "relationship"}:
            raise WorkspaceError("invalid semantic thread anchor kind")
        if self.source_side not in {"current", "proposed"}:
            raise WorkspaceError("invalid semantic thread anchor side")
        for value, field in (
            (self.target_key, "target key"),
            (self.repository_key, "repository key"),
            (self.revision, "revision"),
            (self.review_unit_id, "review unit ID"),
            (self.reviewed_tuple_digest, "reviewed tuple digest"),
            (self.original_source_reference, "original source reference"),
            (self.original_diff_link, "original diff link"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise WorkspaceError(f"semantic thread anchor {field} must be nonempty")
        if self.kind == "view":
            if self.view_key != self.target_key or not self.level:
                raise WorkspaceError("view anchor requires its exact view key and level")
        elif self.view_key is not None or self.level is not None:
            raise WorkspaceError("only view anchors carry view key and level")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: object) -> "SemanticThreadAnchor":
        if not isinstance(raw, dict):
            raise WorkspaceError("invalid semantic thread anchor")
        fields = {
            "version", "kind", "target_key", "view_key", "level", "source_side",
            "repository_key", "revision", "review_unit_id", "reviewed_tuple_digest",
            "original_source_reference", "original_diff_link",
        }
        if set(raw) != fields:
            raise WorkspaceError("invalid semantic thread anchor fields")
        return cls(**raw)  # type: ignore[arg-type]


@dataclass(frozen=True)
class SemanticThread:
    id: str
    body: str
    author: str
    state: Literal["open", "resolved"]
    blocking: bool
    anchor: SemanticThreadAnchor
    freshness: AnchorFreshness
    outdated_reason: str | None


def build_semantic_thread_anchor(
    payload: C4ReviewPayload,
    *,
    kind: AnchorKind,
    target_key: str,
    source_side: AnchorSide,
    view_key: str | None = None,
    level: str | None = None,
) -> SemanticThreadAnchor:
    """Build an anchor only from exact data exposed by a pinned review payload."""

    side = _anchor_repository(payload, kind, source_side)
    exact_view_key = target_key if kind == "view" else view_key
    source_reference = _validate_target(
        payload, kind, target_key, source_side, view_key=exact_view_key, level=level
    )
    diff_link = payload.diffs.get("source")
    if not isinstance(diff_link, str) or not diff_link.strip():
        raise WorkspaceError("review payload has no exact source diff")
    return SemanticThreadAnchor(
        version=1,
        kind=kind,
        target_key=target_key,
        view_key=target_key if kind == "view" else None,
        level=level if kind == "view" else None,
        source_side=source_side,
        repository_key=side["repository_key"],
        revision=side["revision"],
        review_unit_id=payload.review_unit_id,
        reviewed_tuple_digest=payload.reviewed_tuple_digest,
        original_source_reference=source_reference,
        original_diff_link=diff_link,
    )


def create_semantic_thread(
    payload: C4ReviewPayload,
    anchor: SemanticThreadAnchor,
    body: str,
    blocking: bool,
    *,
    owner: str,
    author: str,
    root: Path,
) -> str:
    """Validate and append a semantic root through the existing comment store."""

    _authorize(payload, owner)
    _validate_anchor(payload, anchor)
    return comment(
        payload.owner_work_id,
        "semantic-review",
        body,
        blocking=blocking,
        semantic_anchor=anchor.to_dict(),
        author=author,
        root=root,
    )


def read_semantic_threads(
    payload: C4ReviewPayload,
    *,
    owner: str,
    root: Path,
) -> tuple[SemanticThread, ...]:
    """Read durable roots and resolve freshness without rewriting their anchors."""

    _authorize(payload, owner)
    result: list[SemanticThread] = []
    for row in read_comments(payload.owner_work_id, root=root):
        if row.parent is not None or row.semantic_anchor is None:
            continue
        try:
            anchor = SemanticThreadAnchor.from_dict(row.semantic_anchor)
        except (TypeError, WorkspaceError):
            continue
        freshness, reason = _resolve_freshness(payload, anchor)
        result.append(
            SemanticThread(
                row.id, row.body, row.author, row.state, row.blocking,
                anchor, freshness, reason,
            )
        )
    return tuple(result)


def _authorize(payload: C4ReviewPayload, owner: str) -> None:
    if owner != payload.authorized_owner:
        raise WorkspaceError("semantic review threads are outside the requested owner scope")


def _validate_anchor(payload: C4ReviewPayload, anchor: SemanticThreadAnchor) -> None:
    if (
        anchor.review_unit_id != payload.review_unit_id
        or anchor.reviewed_tuple_digest != payload.reviewed_tuple_digest
    ):
        raise WorkspaceError("semantic thread anchor names a different reviewed tuple")
    side = _anchor_repository(payload, anchor.kind, anchor.source_side)
    if anchor.repository_key != side["repository_key"] or anchor.revision != side["revision"]:
        raise WorkspaceError("semantic thread anchor names a different repository revision")
    expected_source = _validate_target(
        payload,
        anchor.kind,
        anchor.target_key,
        anchor.source_side,
        view_key=anchor.view_key,
        level=anchor.level,
    )
    if anchor.original_source_reference != expected_source:
        raise WorkspaceError("semantic thread anchor source reference is not pinned")
    if anchor.original_diff_link != payload.diffs.get("source"):
        raise WorkspaceError("semantic thread anchor diff link is not pinned")


def _resolve_freshness(
    payload: C4ReviewPayload, anchor: SemanticThreadAnchor
) -> tuple[AnchorFreshness, str | None]:
    try:
        side = _anchor_repository(payload, anchor.kind, anchor.source_side)
    except WorkspaceError:
        return "outdated", "source_side_missing"
    if anchor.repository_key != side["repository_key"]:
        return "outdated", "repository_mismatch"
    if anchor.revision != side["revision"]:
        return "outdated", "revision_mismatch"
    try:
        _validate_target(
            payload,
            anchor.kind,
            anchor.target_key,
            anchor.source_side,
            view_key=anchor.view_key,
            level=anchor.level,
        )
    except WorkspaceError:
        if anchor.kind in {"element", "relationship"} and _has_reviewed_continuity(
            payload, anchor
        ):
            return "current", None
        return "outdated", "target_missing_or_renamed"
    if (
        anchor.review_unit_id != payload.review_unit_id
        or anchor.reviewed_tuple_digest != payload.reviewed_tuple_digest
    ):
        return "outdated", "review_tuple_mismatch"
    return "current", None


def _repository_side(payload: C4ReviewPayload, source_side: AnchorSide) -> dict[str, str]:
    for row in payload.repositories:
        if row.get("side") == source_side:
            repository = row.get("repository_key")
            revision = row.get("revision")
            if repository and revision:
                return row
    raise WorkspaceError(f"review payload has no {source_side} repository revision")


def _anchor_repository(
    payload: C4ReviewPayload, kind: AnchorKind, source_side: AnchorSide
) -> dict[str, str]:
    """Return the pinned repository which actually owns an anchor target.

    Requirements live in the pinned plan document, not in either rendered model
    repository.  Older direct-composer payloads did not expose plan provenance,
    so retain their side-based behavior for compatibility; store-backed HTTP
    payloads always carry the complete plan descriptor.
    """

    if kind == "requirement":
        provenance = payload.provenance
        plan = provenance.get("plan") if isinstance(provenance, dict) else None
        if isinstance(plan, dict):
            repository = plan.get("repository_key")
            revision = plan.get("revision")
            if isinstance(repository, str) and repository and isinstance(revision, str) and revision:
                return {"repository_key": repository, "revision": revision}
    return _repository_side(payload, source_side)


def _validate_target(
    payload: C4ReviewPayload,
    kind: AnchorKind,
    target_key: str,
    source_side: AnchorSide,
    *,
    view_key: str | None,
    level: str | None,
) -> str:
    if payload.state == "error":
        raise WorkspaceError("cannot anchor an invalid review payload")
    if kind == "requirement":
        if target_key not in payload.requirements:
            raise WorkspaceError("requirement is not in the pinned review payload")
        plan = payload.diffs.get("plan")
        if not isinstance(plan, str) or not plan:
            raise WorkspaceError("review payload has no pinned plan reference")
        return plan
    if kind == "view":
        if view_key != target_key or not level:
            raise WorkspaceError("view anchor requires exact key and level")
        for view in payload.views:
            side: C4ReviewSide | None = getattr(view, source_side)
            if view.key == view_key and view.level == level and side is not None:
                return side.svg
        raise WorkspaceError("view is absent from the pinned review side")
    if view_key is not None or level is not None:
        raise WorkspaceError("model target anchors do not use heading or view anchors")
    for view in payload.views:
        side = getattr(view, source_side)
        if side is None:
            continue
        if any(target.kind == kind and target.semantic_id == target_key for target in side.targets):
            return side.svg
    raise WorkspaceError(f"{kind} is absent from the pinned review side")


def _has_reviewed_continuity(payload: C4ReviewPayload, anchor: SemanticThreadAnchor) -> bool:
    model = payload.diffs.get("model")
    identities = model.get("identities") if isinstance(model, dict) else None
    if not isinstance(identities, list):
        return False
    replacements = {
        row.get("semantic_id")
        for row in identities
        if isinstance(row, dict)
        and row.get("kind") == anchor.kind
        and row.get("previous_semantic_id") == anchor.target_key
    }
    if not replacements:
        return False
    for view in payload.views:
        side = getattr(view, anchor.source_side)
        if side is not None and any(
            target.kind == anchor.kind and target.semantic_id in replacements
            for target in side.targets
        ):
            return True
    return False
