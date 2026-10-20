"""Feature-scoped read_doc / write_doc / list_children."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import list_board, read_doc, write_doc
from cascade.board.types import WorkDoc, WorkMeta

from cascade.feature.checkout import feature_checkout_root
from cascade.feature.guard import FeatureToolDenied, tool_guard

_COMMENT_PREFIX = "_comments/"


def comment_work_id(doc_id: str) -> str:
    """Work id convention for reading a feature's own comment JSONL sidecar."""

    return f"{_COMMENT_PREFIX}{doc_id}"


def _read_comment_sidecar(*, feature_id: str, root: Path) -> WorkDoc:
    trunk = Path(root).resolve()
    checkout = feature_checkout_root(feature_id, trunk=trunk)
    sidecar = (checkout / "docs" / "_comments" / f"{feature_id}.jsonl").resolve()
    if not tool_guard(sidecar, "read", feature_id=feature_id, root=trunk):
        raise FeatureToolDenied(f"read denied for {sidecar}")
    feature = read_doc(feature_id, root=checkout)
    if sidecar.is_file():
        body = sidecar.read_text(encoding="utf-8")
    else:
        body = ""
    return WorkDoc(
        meta=WorkMeta(
            id=comment_work_id(feature_id),
            title=f"Comments for {feature_id}",
            tier="feature",
            status="active",
            parent=feature_id,
            children=[],
            depends_on=[],
            owners=[],
            skills=[],
            parent_rev=None,
            created=feature.meta.created,
            updated=feature.meta.updated,
            path=sidecar,
        ),
        body=body,
        sha=None,
    )


def _load_feature(feature_id: str, root: Path):
    trunk = Path(root).resolve()
    checkout = feature_checkout_root(feature_id, trunk=trunk)
    try:
        feature = read_doc(feature_id, root=checkout)
    except NotFound:
        try:
            feature = read_doc(feature_id, root=trunk)
        except NotFound:
            raise FeatureToolDenied(f"unknown feature {feature_id}") from None
    if feature.meta.tier != "feature":
        raise FeatureToolDenied(f"{feature_id} is not a feature")
    return feature


def feature_read_doc(work_id: str, *, feature_id: str, root: Path) -> WorkDoc:
    """Read a work doc if the Feature team is allowed to see it."""

    repo = Path(root).resolve()
    feature = _load_feature(feature_id, repo)

    if work_id.startswith(("_war_room/", "_queue/", "_amendments/")):
        raise FeatureToolDenied(f"read denied for sidecar {work_id!r}")

    if work_id.startswith(_COMMENT_PREFIX):
        doc_id = work_id[len(_COMMENT_PREFIX) :]
        if doc_id != feature_id:
            raise FeatureToolDenied(f"comment read denied for {work_id}")
        return _read_comment_sidecar(feature_id=feature_id, root=repo)

    parent_id = feature.meta.parent
    if parent_id is not None and work_id == parent_id:
        if feature.meta.parent_rev is None:
            raise FeatureToolDenied(
                "parent epic read requires parent_rev; pin on boot or via pin_parent"
            )
        doc = read_doc(parent_id, rev=feature.meta.parent_rev, root=repo)
        if doc.meta.tier != "epic":
            raise FeatureToolDenied(f"{parent_id} is not an epic")
        live_path = read_doc(parent_id, root=repo).meta.path
        if not tool_guard(live_path, "read", feature_id=feature_id, root=repo):
            raise FeatureToolDenied(f"read denied for {live_path}")
        return doc

    try:
        doc = read_doc(work_id, root=repo)
    except NotFound:
        raise FeatureToolDenied(f"unknown work id {work_id}") from None

    if doc.meta.tier == "epic":
        raise FeatureToolDenied(f"feature team cannot read epic {work_id}")
    if doc.meta.tier == "feature" and doc.meta.id != feature_id:
        raise FeatureToolDenied(f"feature team cannot read feature {work_id}")
    if doc.meta.tier == "task" and doc.meta.parent != feature_id:
        raise FeatureToolDenied(f"feature team cannot read task {work_id}")

    if not tool_guard(doc.meta.path, "read", feature_id=feature_id, root=repo):
        raise FeatureToolDenied(f"read denied for {doc.meta.path}")
    return doc


def feature_write_doc(doc: WorkDoc, *, feature_id: str, root: Path) -> str | None:
    """Write only this feature's own markdown doc (not tasks or epics)."""

    repo = Path(root).resolve()
    _load_feature(feature_id, repo)

    if doc.meta.tier != "feature":
        raise FeatureToolDenied(
            f"feature team cannot write {doc.meta.tier} {doc.meta.id}"
        )
    if doc.meta.id != feature_id:
        raise FeatureToolDenied(
            f"write denied: doc id {doc.meta.id!r} != active feature {feature_id!r}"
        )
    current = read_doc(feature_id, root=repo)
    if current.meta.status == "blocked" and doc.meta.status != "blocked":
        raise FeatureToolDenied(
            f"feature {feature_id} is blocked awaiting amendment resolution; "
            "cannot change status away from blocked"
        )
    if not tool_guard(doc.meta.path, "write", feature_id=feature_id, root=repo):
        raise FeatureToolDenied(f"write denied for {doc.meta.path}")
    checkout = feature_checkout_root(feature_id, trunk=repo)
    return write_doc(doc, root=checkout if doc.meta.path.resolve().is_relative_to(checkout) else repo)


def list_children(*, feature_id: str, root: Path) -> list[WorkMeta]:
    """Return task-tier children owned by this feature."""

    trunk = Path(root).resolve()
    _load_feature(feature_id, trunk)
    board = list_board(feature_checkout_root(feature_id, trunk=trunk))
    result = [
        meta
        for meta in board.by_id.values()
        if meta.tier == "task" and meta.parent == feature_id
    ]
    result.sort(key=lambda meta: meta.id)
    return result
