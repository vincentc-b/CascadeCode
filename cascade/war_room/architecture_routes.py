"""Revision-pinned architecture review HTTP projections.

The durable review store is the manifest.  Public identifiers are hashes of
stored descriptors; clients never provide repository paths or git revisions.
Every read rebuilds the descriptor from the authorized review unit before
touching Git or a rendered artifact.
"""

from __future__ import annotations

import hashlib
import difflib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

from cascade.board.context import get_project_context
from cascade.workspace.architecture_review import (
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    ReviewApprovalContext,
    review_lineage_revision,
)
from cascade.workspace.c4_review import C4ReviewPayload, resolve_c4_review_payload
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.architecture_browsing import (
    ArchitectureBrowsingError,
    resolve_architecture_code_context,
)
from cascade.workspace.architecture_snapshots import (
    ArchitectureBrowsingSnapshot,
    ArchitectureSnapshotStore,
    _snapshot_id,
)
from cascade.workspace.c4_bindings import C4BindingError, validate_hit_target_manifest
from cascade.workspace.c4_documentation import (
    C4ContextSelection,
    ContextDocument,
    DesignContext,
    PinnedContextRevision,
    PinnedSourceSection,
    resolve_c4_documentation_context,
    review_documentation_evidence,
    snapshot_documentation_evidence,
)
from cascade.workspace.c4_scheduler import C4RenderScheduler
from cascade.workspace.c4_review import (
    _read_semantic_workspace,
    _semantic_svg,
    _semantic_targets,
    _view_levels,
)
from cascade.workspace.types import ProjectContext, RepositoryContext

MAX_METADATA_BYTES = 256 * 1024
MAX_SVG_BYTES = 4 * 1024 * 1024
MAX_RESOURCE_BYTES = 1024 * 1024
MAX_BROWSING_VIEWS = 100


class ArchitectureHTTPError(WorkspaceError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


def project_for(root: Path) -> ProjectContext:
    return get_project_context() or ProjectContext.colocated(root)


def context_catalog(root: Path) -> dict[str, object]:
    """Return only the War Room target and its registered project worktrees."""

    from cascade.workspace.architecture_browsing import architecture_context_catalog

    return architecture_context_catalog(project_for(root), root).to_dict()


def create_snapshot(
    root: Path,
    body: dict[str, object],
    *,
    scheduler: C4RenderScheduler | None = None,
) -> tuple[int, dict[str, object]]:
    """Create one snapshot from catalog-issued identifiers only."""

    allowed = {"context_id", "documentation_ref_id", "code_directory"}
    if set(body) - allowed:
        raise ArchitectureHTTPError(400, "unknown snapshot creation field")
    values: dict[str, str | None] = {}
    for field in allowed:
        value = body.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ArchitectureHTTPError(400, f"invalid {field}")
        values[field] = value.strip() if isinstance(value, str) else None
    try:
        with ArchitectureSnapshotStore(project_for(root), root, scheduler=scheduler) as store:
            snapshot = store.create(
                values["context_id"],
                documentation_ref_id=values["documentation_ref_id"],
                code_directory=values["code_directory"] or ".",
            )
            payload = _snapshot_projection(store, snapshot, cursor=0, limit=25)
    except ArchitectureBrowsingError as exc:
        raise ArchitectureHTTPError(404, str(exc)) from exc
    except C4BindingError as exc:
        raise ArchitectureHTTPError(409, str(exc)) from exc
    if snapshot.reason_code == "queue_full":
        return 429, payload
    return (202 if snapshot.state == "pending" else 200), payload


def snapshot_projection(
    root: Path,
    snapshot_id: str,
    *,
    cursor: int = 0,
    limit: int = 25,
    view_key: str | None = None,
    level: str | None = None,
    semantic_target: str | None = None,
    scheduler: C4RenderScheduler | None = None,
) -> tuple[int, dict[str, object]]:
    if cursor < 0 or limit < 1 or limit > MAX_BROWSING_VIEWS:
        raise ArchitectureHTTPError(400, "invalid snapshot pagination")
    try:
        with ArchitectureSnapshotStore(project_for(root), root, scheduler=scheduler) as store:
            snapshot = _authorized_snapshot(store, snapshot_id)
            payload = _snapshot_projection(
                store,
                snapshot,
                cursor=cursor,
                limit=limit,
                view_key=view_key,
                level=level,
                semantic_target=semantic_target,
            )
    except KeyError as exc:
        raise ArchitectureHTTPError(404, "architecture snapshot not found") from exc
    except (C4BindingError, json.JSONDecodeError) as exc:
        raise ArchitectureHTTPError(409, str(exc)) from exc
    return (202 if snapshot.state == "pending" else 200), payload


def snapshot_head_status(
    root: Path,
    snapshot_id: str,
    *,
    scheduler: C4RenderScheduler | None = None,
) -> dict[str, object]:
    try:
        with ArchitectureSnapshotStore(project_for(root), root, scheduler=scheduler) as store:
            snapshot = _authorized_snapshot(store, snapshot_id)
            return {
                "schema_version": 1,
                "snapshot_id": snapshot.snapshot_id,
                **store.head_status(snapshot_id),
            }
    except KeyError as exc:
        raise ArchitectureHTTPError(404, "architecture snapshot not found") from exc


def _authorized_snapshot(
    store: ArchitectureSnapshotStore, snapshot_id: str
) -> ArchitectureBrowsingSnapshot:
    snapshot = store.get(snapshot_id)
    expected = _snapshot_id(
        snapshot.descriptor
        if snapshot.render_operation_id is not None
        else {**snapshot.descriptor, "failure": snapshot.reason_code}
    )
    if expected != snapshot.snapshot_id:
        raise ArchitectureHTTPError(409, "architecture snapshot descriptor changed")
    context = snapshot.descriptor.get("context")
    if not isinstance(context, dict) or not isinstance(context.get("context_id"), str):
        raise ArchitectureHTTPError(409, "architecture snapshot context is invalid")
    try:
        current = resolve_architecture_code_context(
            store.project, store.session_target, context["context_id"]
        )
    except ArchitectureBrowsingError as exc:
        raise ArchitectureHTTPError(409, str(exc)) from exc
    if (
        current.repository_key != context.get("repository_key")
        or current.kind != context.get("kind")
    ):
        raise ArchitectureHTTPError(409, "architecture snapshot context identity changed")
    return snapshot


def _snapshot_projection(
    store: ArchitectureSnapshotStore,
    snapshot: ArchitectureBrowsingSnapshot,
    *,
    cursor: int,
    limit: int,
    view_key: str | None = None,
    level: str | None = None,
    semantic_target: str | None = None,
) -> dict[str, object]:
    descriptor = snapshot.descriptor
    payload: dict[str, object] = {
        "schema_version": 1,
        "snapshot_id": snapshot.snapshot_id,
        "state": snapshot.state,
        "reason_code": snapshot.reason_code,
        "message": snapshot.message,
        "context": descriptor.get("context"),
        "code_directory": descriptor.get("code_directory"),
        "provenance": {
            "repositories": descriptor.get("repositories"),
            "revisions": descriptor.get("revisions"),
            "association": descriptor.get("association"),
            "accepted_lineage": descriptor.get("accepted_lineage"),
            "architecture_destination": descriptor.get("architecture_destination"),
        },
        "views": [],
        "targets": [],
        "resources": _snapshot_resources(snapshot),
        "initial_view": None,
        "selected": {
            "view_key": view_key,
            "level": level,
            "semantic_target": semantic_target,
        },
        "associated_review": _associated_review(store.project, snapshot),
        "documentation_context_url": (
            f"/api/architecture/snapshots/{snapshot.snapshot_id}/context"
        ),
    }
    if snapshot.state != "ready":
        payload["pagination"] = {
            "cursor": cursor, "limit": limit, "total": 0, "next_cursor": None,
        }
        return _bounded_snapshot_payload(payload)

    operation_id = snapshot.render_operation_id
    if operation_id is None:
        raise ArchitectureHTTPError(409, "ready snapshot has no render operation")
    artifact = store.scheduler.get_semantic_artifact(
        operation_id, artifact_ref=snapshot.snapshot_id
    )
    render = artifact.render
    if render.binding_manifest is None or render.artifact_directory is None:
        raise C4BindingError("rendered snapshot has no hit-target manifest")
    workspace = _read_semantic_workspace(artifact)
    manifest = json.loads(render.binding_manifest.read_text(encoding="utf-8"))
    artifact_root = render.binding_manifest.parent.resolve()
    try:
        artifact_root.relative_to(render.artifact_directory.resolve())
    except ValueError as exc:
        raise C4BindingError("snapshot hit-target manifest escapes the render") from exc
    validate_hit_target_manifest(
        workspace=workspace,
        manifest=manifest,
        artifact_root=artifact_root,
        expected_view_keys=render.view_keys,
        expected_semantic_ids=artifact.contract.semantic_ids,
    )
    levels = _view_levels(workspace, render.view_keys)
    rows = {row["view_key"]: row for row in manifest["views"]}
    targets = _semantic_targets(workspace)
    memberships: dict[str, list[dict[str, str]]] = {}
    views: list[dict[str, object]] = []
    for key in render.view_keys:
        row = rows[key]
        descriptor_row = {
            "kind": "snapshot_svg",
            "scope": snapshot.snapshot_id,
            "render_identity": descriptor["render"]["identity"],
            "view_key": key,
            "level": levels[key],
        }
        target_ids = sorted({str(item["semantic_id"]) for item in row["targets"]})
        views.append({
            "key": key,
            "level": levels[key],
            "artifact_url": (
                f"/api/architecture/artifacts/{snapshot.snapshot_id}/"
                f"{_opaque_id(descriptor_row)}"
            ),
            "target_ids": target_ids,
        })
        for target_id in target_ids:
            memberships.setdefault(target_id, []).append({
                "view_key": key,
                "level": levels[key],
                "label": f"{key} ({levels[key]})",
            })
    # A selected parent may drill to any view containing a descendant.  The
    # ancestry comes from the validated semantic workspace, never SVG labels.
    for target_id, choices in tuple(memberships.items()):
        seen: set[str] = set()
        parent = targets[target_id].parent if target_id in targets else None
        while parent is not None and parent not in seen:
            seen.add(parent)
            inherited = memberships.setdefault(parent, [])
            for choice in choices:
                if choice not in inherited:
                    inherited.append(choice)
            parent = targets[parent].parent if parent in targets else None
    if (view_key is None) != (level is None):
        raise ArchitectureHTTPError(400, "snapshot view and level must be selected together")
    if view_key is not None and not any(
        item["key"] == view_key and item["level"] == level for item in views
    ):
        raise ArchitectureHTTPError(400, "invalid snapshot view selection")
    if semantic_target is not None and semantic_target not in targets:
        raise ArchitectureHTTPError(400, "invalid semantic target")
    public_targets = []
    for target_id in sorted(targets):
        target = targets[target_id]
        public_targets.append({
            "kind": target.kind,
            "semantic_id": target.semantic_id,
            "label": target.label,
            "source": target.source,
            "destination": target.destination,
            "drill_choices": memberships.get(target_id, []),
        })
    initial = next(
        (item for item in views if item["level"] in {"systemLandscapeViews", "systemContextViews"}),
        views[0] if views else None,
    )
    page = views[cursor:cursor + limit]
    payload.update({
        "views": page,
        "targets": public_targets,
        "initial_view": (
            {"view_key": initial["key"], "level": initial["level"]}
            if initial else None
        ),
        "pagination": {
            "cursor": cursor,
            "limit": limit,
            "total": len(views),
            "next_cursor": cursor + len(page) if cursor + len(page) < len(views) else None,
        },
    })
    return _bounded_snapshot_payload(payload)


def _snapshot_resources(snapshot: ArchitectureBrowsingSnapshot) -> list[dict[str, object]]:
    rows = _snapshot_resource_descriptors(snapshot)
    return [
        {
            "kind": row["kind"], "path": row["path"], "revision": row["revision"],
            "url": f"/api/architecture/resources/{snapshot.snapshot_id}/{_opaque_id(row)}",
        }
        for row in rows
    ]


def _snapshot_resource_descriptors(
    snapshot: ArchitectureBrowsingSnapshot,
) -> list[dict[str, object]]:
    descriptor = snapshot.descriptor
    rows: list[dict[str, object]] = []
    mapping = descriptor.get("mapping")
    if isinstance(mapping, dict):
        rows.append({
            "kind": "mapping", "repository_role": "target",
            "repository_key": mapping.get("repository_key"),
            "revision": mapping.get("revision"), "path": mapping.get("path"),
            "digest": mapping.get("sha256"), "scope": snapshot.snapshot_id,
        })
    closure = descriptor.get("source_closure")
    revisions = descriptor.get("revisions")
    repositories = descriptor.get("repositories")
    if isinstance(closure, dict) and isinstance(closure.get("files"), list):
        for index, item in enumerate(closure["files"]):
            if not isinstance(item, dict):
                continue
            rows.append({
                "kind": "model" if index == 0 else "source",
                "repository_role": descriptor.get("architecture_destination"),
                "repository_key": repositories.get("documentation") if isinstance(repositories, dict) else None,
                "revision": revisions.get("documentation") if isinstance(revisions, dict) else None,
                "path": item.get("path"), "digest": item.get("sha256"),
                "scope": snapshot.snapshot_id,
            })
    return rows


def _associated_review(
    project: ProjectContext, snapshot: ArchitectureBrowsingSnapshot
) -> dict[str, str] | None:
    context = snapshot.descriptor.get("context")
    revisions = snapshot.descriptor.get("revisions")
    if not isinstance(context, dict) or not isinstance(revisions, dict):
        return None
    work_id = context.get("work_id")
    if not isinstance(work_id, str) or not work_id:
        return None
    matches = []
    for unit in ArchitectureReviewStore(project).units_affecting(work_id):
        model = unit.proposed_model
        if (
            unit.owner_work_id == work_id
            and model is not None
            and model.contract.reference.revision == revisions.get("documentation")
            and unit.code_repository_key == context.get("repository_key")
        ):
            matches.append(unit)
    if len(matches) != 1:
        return None
    unit = matches[0]
    return {
        "work_id": unit.owner_work_id,
        "review_unit_id": unit.review_unit_id,
        "url": f"/api/architecture/reviews/{unit.owner_work_id}",
    }


def _bounded_snapshot_payload(payload: dict[str, object]) -> dict[str, object]:
    if len(json.dumps(payload, separators=(",", ":")).encode()) > MAX_METADATA_BYTES:
        raise ArchitectureHTTPError(413, "architecture snapshot page exceeds 256 KiB")
    return payload


def review_envelope(root: Path, work_id: str, tier: str) -> dict[str, object] | None:
    if tier not in {"epic", "feature"}:
        return None
    try:
        payload = _resolve(root, work_id)
        state = payload.state
        code = payload.reason_code or state
        message = payload.reason or payload.summary or "Architecture review is unavailable."
        unit_id = payload.review_unit_id or None
        digest = payload.reviewed_tuple_digest or None
        approval_context = _approval_context(root, payload) if unit_id else None
    except Exception as exc:  # The plan and comments must remain readable.
        state, code = "unavailable", "unavailable"
        message = str(exc) or "Architecture review is unavailable."
        unit_id = digest = None
        approval_context = None
    retryable = state in {"pending", "render_failed", "unavailable"}
    envelope = {
        "schema_version": 1,
        "resource_url": f"/api/architecture/reviews/{work_id}",
        "state": state,
        "reason_code": code,
        "message": message,
        "review_unit_id": unit_id,
        "reviewed_tuple_digest": digest,
        "retry": {
            "retryable": retryable,
            "retry_after_seconds": 5 if retryable else None,
        },
    }
    if approval_context is not None:
        envelope["approval_context"] = approval_context.to_dict()
    return envelope


def review_projection(
    root: Path, work_id: str, *, cursor: int = 0, limit: int = 25
) -> dict[str, object]:
    if cursor < 0 or limit < 1 or limit > 100:
        raise ArchitectureHTTPError(400, "invalid review pagination")
    payload = _resolve(root, work_id)
    value = payload.to_dict()
    approval_context = _approval_context(root, payload) if payload.review_unit_id else None
    value["approval_context"] = (
        approval_context.to_dict() if approval_context is not None else None
    )
    scope = payload.review_unit_id
    views = value.get("views") or []
    page = views[cursor:cursor + limit]
    for view in page:
        for side_name in ("current", "proposed"):
            side = view.get(side_name)
            if not isinstance(side, dict):
                continue
            descriptor = {
                "kind": "svg", "scope": scope, "tuple": payload.reviewed_tuple_digest,
                "view": view["key"], "level": view["level"], "side": side_name,
                "revision": side["revision"], "repository_key": side["repository_key"],
            }
            artifact_id = _opaque_id(descriptor)
            side["svg"] = f"/api/architecture/artifacts/{scope}/{artifact_id}"
    value["views"] = page
    value["pagination"] = {
        "cursor": cursor,
        "limit": limit,
        "total": len(views),
        "next_cursor": cursor + len(page) if cursor + len(page) < len(views) else None,
    }
    resources = []
    if scope and value["approval_context"] is not None:
        unit = _unit_for_scope(root, scope, work_id=work_id)
        resources = _all_resource_descriptors(root, unit)
        value["architecture_impact"] = unit.architecture_impact
        value["impact_reason"] = unit.impact_reason
    elif scope:
        unit = _publication_unit_for_scope(root, scope, work_id=work_id)
        if unit is not None:
            # A superseded publication remains useful evidence, but cannot
            # authorize approval or imply a diff against the current plan.
            resources = _published_design_descriptors(root, unit)
            value["architecture_impact"] = unit.architecture_impact
            value["impact_reason"] = unit.impact_reason
    value["resources"] = [
        {
            "kind": row["kind"], "side": row.get("side"), "path": row["path"],
            "revision": row["revision"],
            "historical": value["approval_context"] is None or payload.state == "stale_revision",
            "baseline_kind": row.get("baseline_kind"),
            "before_revision": row.get("before_revision"),
            "url": f"/api/architecture/resources/{scope}/{_opaque_id(row)}",
        }
        for row in resources
    ]
    value["documentation_context_url"] = (
        f"/api/architecture/reviews/{work_id}/context"
    )
    if isinstance(value.get("diffs"), dict):
        value["diffs"]["resources"] = [
            {
                "kind": row["kind"],
                "url": f"/api/architecture/resources/{scope}/{_opaque_id(row)}",
            }
            for row in resources if row.get("mode") == "diff"
        ]
    encoded = json.dumps(value, separators=(",", ":")).encode()
    if len(encoded) > MAX_METADATA_BYTES:
        raise ArchitectureHTTPError(413, "architecture review page exceeds 256 KiB")
    return value


def review_documentation_projection(
    root: Path,
    work_id: str,
    *,
    side: str,
    view_key: str,
    level: str,
    selection_kind: str = "view",
    semantic_target: str | None = None,
) -> dict[str, object]:
    """Return bounded documentation metadata for one validated review selection."""

    if side not in {"current", "proposed"}:
        raise ArchitectureHTTPError(400, "invalid documentation review side")
    if selection_kind not in {"view", "element", "relationship"}:
        raise ArchitectureHTTPError(400, "invalid documentation selection kind")
    if selection_kind == "view":
        if semantic_target is not None:
            raise ArchitectureHTTPError(400, "a view selection does not accept a target")
        semantic_id = view_key
    else:
        if not semantic_target:
            raise ArchitectureHTTPError(400, "a target selection requires a semantic ID")
        semantic_id = semantic_target

    active = _unit_for_work(root, work_id)
    payload = _resolve_unit(root, active)
    view = next(
        (row for row in payload.views if row.key == view_key and row.level == level),
        None,
    )
    selected_side = getattr(view, side, None) if view is not None else None
    if selected_side is None:
        raise ArchitectureHTTPError(400, "invalid documentation review view or side")
    if selection_kind != "view" and not any(
        row.semantic_id == semantic_id and row.kind == selection_kind
        for row in selected_side.targets
    ):
        raise ArchitectureHTTPError(400, "invalid documentation semantic target")

    source_unit = active if side == "proposed" else _baseline_unit(root, active)
    documents = _review_context_documents(active, source_unit)
    owner_context = (
        (_design_context(source_unit),) if source_unit is not None else ()
    )
    evidence = review_documentation_evidence(
        active,
        documents,
        owner_context=owner_context,
    )
    revisions = {
        (row.repository_key, row.revision) for row in evidence.pinned_revisions
    }
    revisions.update(
        (row.source.repository_key, row.source.revision)
        for row in documents if row.source is not None
    )
    evidence = replace(
        evidence,
        pinned_revisions=tuple(
            PinnedContextRevision(*row) for row in sorted(revisions)
        ),
    )
    selection = C4ContextSelection(
        selection_kind, semantic_id, view_key=view_key, level=level
    )
    value = resolve_c4_documentation_context(evidence, selection).to_dict()
    value["side"] = side
    descriptors = _context_resource_descriptors(root, active)
    _attach_context_urls(value, active.review_unit_id, descriptors, side=side)
    return _bounded_context_payload(value)


def snapshot_documentation_projection(
    root: Path,
    snapshot_id: str,
    *,
    view_key: str,
    level: str,
    selection_kind: str = "view",
    semantic_target: str | None = None,
    scheduler: C4RenderScheduler | None = None,
) -> dict[str, object]:
    """Return documentation metadata bound to an immutable browsing snapshot."""

    if selection_kind not in {"view", "element", "relationship"}:
        raise ArchitectureHTTPError(400, "invalid documentation selection kind")
    if selection_kind == "view":
        if semantic_target is not None:
            raise ArchitectureHTTPError(400, "a view selection does not accept a target")
        semantic_id = view_key
    else:
        if not semantic_target:
            raise ArchitectureHTTPError(400, "a target selection requires a semantic ID")
        semantic_id = semantic_target

    try:
        with ArchitectureSnapshotStore(project_for(root), root, scheduler=scheduler) as store:
            snapshot = _authorized_snapshot(store, snapshot_id)
            if snapshot.state == "documentation_ref_required":
                return {
                    "schema_version": 1,
                    "scope_kind": "snapshot",
                    "scope_id": snapshot.snapshot_id,
                    "state": "documentation_ref_required",
                    "documentation_ref_required": True,
                    "reason": snapshot.message,
                }
            projected = _snapshot_projection(
                store,
                snapshot,
                cursor=0,
                limit=MAX_BROWSING_VIEWS,
                view_key=view_key,
                level=level,
                semantic_target=semantic_target,
            )
            if snapshot.state != "ready":
                raise ArchitectureHTTPError(409, "architecture snapshot is not ready")
            view = next(
                (row for row in projected["views"] if row["key"] == view_key), None
            )
            if view is None:
                raise ArchitectureHTTPError(400, "invalid documentation snapshot view")
            if selection_kind != "view":
                target = next(
                    (
                        row for row in projected["targets"]
                        if row["semantic_id"] == semantic_id
                    ),
                    None,
                )
                if (
                    target is None
                    or target["kind"] != selection_kind
                    or semantic_id not in view["target_ids"]
                ):
                    raise ArchitectureHTTPError(
                        400, "invalid documentation semantic target"
                    )
            unit = _snapshot_associated_unit(store.project, snapshot)
            documents = _review_context_documents(unit, unit) if unit else ()
            associations = (
                review_documentation_evidence(unit, documents).associations
                if unit else ()
            )
            owner_context = _snapshot_owner_context(store.project, snapshot)
            evidence = snapshot_documentation_evidence(
                snapshot.snapshot_id,
                snapshot.descriptor,
                documents,
                associations,
                owner_context=owner_context,
            )
            value = resolve_c4_documentation_context(
                evidence,
                C4ContextSelection(
                    selection_kind, semantic_id, view_key=view_key, level=level
                ),
            ).to_dict()
            descriptors = _snapshot_context_resource_descriptors(
                store.project, snapshot, unit
            )
            _attach_context_urls(value, snapshot.snapshot_id, descriptors)
            return _bounded_context_payload(value)
    except KeyError as exc:
        raise ArchitectureHTTPError(404, "architecture snapshot not found") from exc


def resolve_review_context(root: Path, work_id: str) -> C4ReviewPayload:
    """Resolve the authoritative active review tuple for another HTTP slice."""

    payload = _resolve(root, work_id)
    public_views = []
    for view in payload.views:
        sides = {}
        for side_name in ("current", "proposed"):
            side = getattr(view, side_name)
            if side is None:
                sides[side_name] = None
                continue
            descriptor = {
                "kind": "svg",
                "scope": payload.review_unit_id,
                "tuple": payload.reviewed_tuple_digest,
                "view": view.key,
                "level": view.level,
                "side": side_name,
                "revision": side.revision,
                "repository_key": side.repository_key,
            }
            sides[side_name] = replace(
                side,
                svg=(
                    f"/api/architecture/artifacts/{payload.review_unit_id}/"
                    f"{_opaque_id(descriptor)}"
                ),
            )
        public_views.append(replace(view, **sides))
    return replace(payload, views=tuple(public_views))


def _unit_for_work(root: Path, work_id: str) -> ArchitectureReviewUnit:
    units = [
        unit
        for unit in ArchitectureReviewStore(project_for(root)).units_affecting(work_id)
        if unit.owner_work_id == work_id
    ]
    if not units:
        raise ArchitectureHTTPError(404, "architecture review not found")
    return units[-1]


def _baseline_unit(
    root: Path, unit: ArchitectureReviewUnit
) -> ArchitectureReviewUnit | None:
    baseline_id = unit.accepted_baseline.accepted_review_unit_id
    return (
        ArchitectureReviewStore(project_for(root)).get(baseline_id)
        if baseline_id else None
    )


def _design_context(unit: ArchitectureReviewUnit) -> DesignContext:
    artifact = unit.design
    reference = artifact.reference
    return DesignContext(
        unit.code_directory,
        unit.design_owner_directory,
        PinnedSourceSection(
            reference.destination_repository_key,
            reference.revision,
            reference.repository_path,
            content_digest=artifact.content_digest,
        ),
    )


def _review_context_documents(
    association_unit: ArchitectureReviewUnit | None,
    source_unit: ArchitectureReviewUnit | None,
) -> tuple[ContextDocument, ...]:
    """Project citations onto their pinned work-document source records."""

    if association_unit is None:
        return ()
    rows: list[ContextDocument] = []
    for kind, identifiers in (
        ("requirement", association_unit.requirement_citations),
        ("decision", association_unit.decision_citations),
    ):
        for document_id in identifiers:
            source = None
            if source_unit is not None:
                # Requirement and decision citations are records in the pinned
                # work plan.  DESIGN.md is ownership context, not citation
                # provenance, and must never be reused for semantic anchors.
                pinned = source_unit.plan
                source = PinnedSourceSection(
                    pinned.repository_key,
                    pinned.revision,
                    pinned.path,
                    document_id,
                    pinned.content_digest,
                )
            rows.append(
                ContextDocument(
                    document_id,
                    kind,
                    document_id,
                    source,
                    state="available" if source is not None else "missing",
                    reason=None if source is not None else "counterpart_missing",
                )
            )
    return tuple(rows)


def _context_resource_descriptors(
    root: Path, unit: ArchitectureReviewUnit
) -> list[dict[str, object]]:
    """Enumerate only resources derivable from the active reviewed tuple."""

    sides = {
        "proposed": unit,
        "current": _baseline_unit(root, unit),
    }
    rows: list[dict[str, object]] = []
    for side, source_unit in sides.items():
        if source_unit is None:
            continue
        documents = _review_context_documents(unit, source_unit)
        for document in documents:
            assert document.source is not None
            source = document.source
            role = source_unit.plan.repository_role
            base: dict[str, object] = {
                "kind": "context_document",
                "scope": unit.review_unit_id,
                "side": side,
                "document_id": document.document_id,
                "document_kind": document.kind,
                "repository_role": role,
                "repository_key": source.repository_key,
                "revision": source.revision,
                "path": source.path.as_posix(),
                "digest": source.content_digest,
            }
            rows.append({**base, "mode": "document"})
            rows.append({**base, "mode": "section", "section": source.section})

    for document_id in (*unit.requirement_citations, *unit.decision_citations):
        proposed = next(
            (
                row for row in rows
                if row["side"] == "proposed"
                and row["document_id"] == document_id
                and row["mode"] == "document"
            ),
            None,
        )
        current = next(
            (
                row for row in rows
                if row["side"] == "current"
                and row["document_id"] == document_id
                and row["mode"] == "document"
            ),
            None,
        )
        if proposed is not None and current is not None:
            rows.append({
                **proposed,
                "kind": "context_document_diff",
                "mode": "diff",
                "before_revision": current["revision"],
                "before_path": current["path"],
                "before_digest": current["digest"],
                "before_repository_role": current["repository_role"],
                "before_repository_key": current["repository_key"],
            })
    return rows


def _snapshot_associated_unit(
    project: ProjectContext, snapshot: ArchitectureBrowsingSnapshot
) -> ArchitectureReviewUnit | None:
    row = _associated_review(project, snapshot)
    if row is None:
        return None
    unit = ArchitectureReviewStore(project).get(row["review_unit_id"])
    if unit is None:
        return None
    descriptor = snapshot.descriptor
    association = descriptor.get("association")
    revisions = descriptor.get("revisions")
    accepted = descriptor.get("accepted_lineage")
    if not isinstance(association, dict) or not isinstance(revisions, dict):
        return None
    evidence_id = association.get("evidence_id")
    if evidence_id == unit.review_unit_id:
        return unit
    if (
        association.get("provenance") == "colocated"
        and revisions.get("code") == revisions.get("documentation")
    ):
        return unit
    if isinstance(accepted, dict) and accepted.get("review_unit_id") == unit.review_unit_id:
        return unit
    return None


def _snapshot_owner_context(
    project: ProjectContext, snapshot: ArchitectureBrowsingSnapshot
) -> tuple[DesignContext, ...]:
    descriptor = snapshot.descriptor
    revisions = descriptor.get("revisions")
    repositories = descriptor.get("repositories")
    if not isinstance(revisions, dict) or not isinstance(repositories, dict):
        return ()
    code_directory = Path(str(descriptor.get("code_directory") or "."))
    owner_directory = Path(
        str(descriptor.get("design_owner_directory") or code_directory.as_posix())
    )
    # Snapshot creation has already resolved the directory through the pinned
    # ownership mapping; the documentation path convention is deterministic.
    if descriptor.get("architecture_destination") == "tracking":
        path = (
            Path("design") / project.target_repository_key /
            owner_directory / "DESIGN.md"
        )
    else:
        path = owner_directory / "DESIGN.md"
    return (
        DesignContext(
            code_directory,
            owner_directory,
            PinnedSourceSection(
                str(repositories["documentation"]),
                str(revisions["documentation"]),
                path,
            ),
        ),
    )


def _snapshot_context_resource_descriptors(
    project: ProjectContext,
    snapshot: ArchitectureBrowsingSnapshot,
    unit: ArchitectureReviewUnit | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    repositories = snapshot.descriptor.get("repositories", {})
    revisions = snapshot.descriptor.get("revisions", {})
    pinned = {
        (str(repositories.get(role)), str(revisions.get(role)))
        for role in ("code", "documentation")
    }
    if unit is not None:
        for row in _context_resource_descriptors_for_unit(unit):
            if (str(row["repository_key"]), str(row["revision"])) in pinned:
                rows.append({**row, "scope": snapshot.snapshot_id})
    for design in _snapshot_owner_context(project, snapshot):
        source = design.source
        rows.append({
            "kind": "context_design",
            "scope": snapshot.snapshot_id,
            "mode": "document",
            "repository_role": snapshot.descriptor["architecture_destination"],
            "repository_key": source.repository_key,
            "revision": source.revision,
            "path": source.path.as_posix(),
            "digest": source.content_digest,
        })
    return rows


def _context_resource_descriptors_for_unit(
    unit: ArchitectureReviewUnit,
) -> list[dict[str, object]]:
    """Proposed-only form used when an exact review is attached to a snapshot."""

    rows: list[dict[str, object]] = []
    for document in _review_context_documents(unit, unit):
        assert document.source is not None
        source = document.source
        role = unit.plan.repository_role
        base = {
            "kind": "context_document",
            "scope": unit.review_unit_id,
            "side": "proposed",
            "document_id": document.document_id,
            "document_kind": document.kind,
            "repository_role": role,
            "repository_key": source.repository_key,
            "revision": source.revision,
            "path": source.path.as_posix(),
            "digest": source.content_digest,
        }
        rows.extend((
            {**base, "mode": "document"},
            {**base, "mode": "section", "section": source.section},
        ))
    return rows


def _attach_context_urls(
    value: dict[str, object],
    scope: str,
    descriptors: list[dict[str, object]],
    *,
    side: str | None = None,
) -> None:
    prefix = f"/api/architecture/resources/{scope}/"
    by_document: dict[str, dict[str, str]] = {}
    for row in descriptors:
        document_id = row.get("document_id")
        if not isinstance(document_id, str):
            continue
        mode = str(row.get("mode"))
        row_side = row.get("side")
        key = (
            "diff_url" if mode == "diff"
            else f"{row_side}_url" if mode == "document" and side is not None
            else "document_url" if mode == "document"
            else "section_url"
        )
        if mode == "section" and side is not None and row_side != side:
            continue
        by_document.setdefault(document_id, {})[key] = prefix + _opaque_id(row)
    for collection in ("explicit_target_links", "view_links"):
        for link in value.get(collection, []):
            link["resources"] = by_document.get(link["document_id"], {})
    design_rows = [row for row in descriptors if row.get("kind") == "context_design"]
    for index, design in enumerate(value.get("owner_context", [])):
        if index < len(design_rows):
            design["document_url"] = prefix + _opaque_id(design_rows[index])


def _bounded_context_payload(value: dict[str, object]) -> dict[str, object]:
    if len(json.dumps(value, separators=(",", ":")).encode()) > MAX_METADATA_BYTES:
        raise ArchitectureHTTPError(413, "architecture context exceeds 256 KiB")
    return value


def _approval_context(root: Path, payload: C4ReviewPayload) -> ReviewApprovalContext | None:
    # Publication failures can retain a proposal ID before it enters the review
    # store. Preserve that diagnostic without advertising an actionable scope.
    if (
        payload.state not in {"ready", "no_diagram_change"}
        and not payload.views
        and ArchitectureReviewStore(project_for(root)).get(payload.review_unit_id) is None
    ):
        return None
    unit = _unit_for_scope(
        root, payload.review_unit_id, work_id=payload.owner_work_id
    )
    if unit.reviewed_tuple_digest != payload.reviewed_tuple_digest:
        raise ArchitectureHTTPError(409, "architecture review binding changed")
    return ReviewApprovalContext(
        unit.owner_work_id,
        unit.target_repository_key,
        unit.plan.revision,
        unit.review_unit_id,
        unit.reviewed_tuple_digest,
        unit.baseline_generation,
    )


def artifact_bytes(
    root: Path,
    scope: str,
    artifact_id: str,
    *,
    scheduler: C4RenderScheduler | None = None,
) -> tuple[bytes, str]:
    if scope.startswith("architecture-snapshot-"):
        return _snapshot_artifact_bytes(root, scope, artifact_id, scheduler=scheduler)
    unit = _unit_for_scope(root, scope)
    payload = _resolve_unit(root, unit)
    if payload.reviewed_tuple_digest != unit.reviewed_tuple_digest:
        raise ArchitectureHTTPError(409, "architecture review binding changed")
    for view in payload.views:
        for side_name in ("current", "proposed"):
            side = getattr(view, side_name)
            if side is None:
                continue
            descriptor = {
                "kind": "svg", "scope": scope, "tuple": payload.reviewed_tuple_digest,
                "view": view.key, "level": view.level, "side": side_name,
                "revision": side.revision, "repository_key": side.repository_key,
            }
            if _opaque_id(descriptor) != artifact_id:
                continue
            body = _sanitize_svg(side.svg)
            if len(body) > MAX_SVG_BYTES:
                raise ArchitectureHTTPError(413, "architecture SVG exceeds 4 MiB")
            return body, _etag(body)
    raise ArchitectureHTTPError(404, "architecture artifact not found")


def resource_bytes(
    root: Path,
    scope: str,
    resource_id: str,
    *,
    scheduler: C4RenderScheduler | None = None,
) -> tuple[bytes, str, str]:
    if scope.startswith("architecture-snapshot-"):
        return _snapshot_resource_bytes(root, scope, resource_id, scheduler=scheduler)
    unit = ArchitectureReviewStore(project_for(root)).get(scope)
    if unit is not None:
        unit = _unit_for_scope(root, scope)
        descriptors = [
            *_all_resource_descriptors(root, unit),
            *_context_resource_descriptors(root, unit),
        ]
    else:
        unit = _publication_unit_for_scope(root, scope)
        if unit is None:
            raise ArchitectureHTTPError(404, "architecture scope not found")
        descriptors = _published_design_descriptors(root, unit)
    for descriptor in descriptors:
        if _opaque_id(descriptor) != resource_id:
            continue
        project = project_for(root)
        body = _read_descriptor_blob(project, descriptor)
        if descriptor.get("mode") == "diff":
            before = b""
            if descriptor.get("before_revision"):
                before_descriptor = {
                    **descriptor,
                    "revision": descriptor["before_revision"],
                    "path": descriptor["before_path"],
                    "digest": descriptor["before_digest"],
                    "repository_role": descriptor.get(
                        "before_repository_role", descriptor["repository_role"]
                    ),
                    "repository_key": descriptor.get(
                        "before_repository_key", descriptor["repository_key"]
                    ),
                }
                before = _read_descriptor_blob(project, before_descriptor)
            try:
                old = before.decode("utf-8").splitlines(keepends=True)
                new = body.decode("utf-8").splitlines(keepends=True)
            except UnicodeDecodeError as exc:
                raise ArchitectureHTTPError(409, "pinned diff resource is not UTF-8") from exc
            body = "".join(difflib.unified_diff(
                old, new,
                fromfile=str(descriptor.get("before_path") or "/dev/null"),
                tofile=descriptor["path"],
                n=max(len(old), len(new)),
            )).encode("utf-8")
        if descriptor.get("mode") == "section":
            body = _markdown_section(body, str(descriptor["section"]))
        if len(body) > MAX_RESOURCE_BYTES:
            raise ArchitectureHTTPError(413, "architecture resource exceeds 1 MiB")
        if descriptor.get("mode") == "diff":
            return body, "text/x-diff; charset=utf-8", _etag(body)
        suffix = Path(str(descriptor["path"])).suffix.lower()
        content_type = {
            ".md": "text/markdown; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".dsl": "text/plain; charset=utf-8",
        }.get(suffix, "text/plain; charset=utf-8")
        return body, content_type, _etag(body)
    raise ArchitectureHTTPError(404, "architecture resource not found")


def _snapshot_artifact_bytes(
    root: Path,
    snapshot_id: str,
    artifact_id: str,
    *,
    scheduler: C4RenderScheduler | None = None,
) -> tuple[bytes, str]:
    try:
        with ArchitectureSnapshotStore(project_for(root), root, scheduler=scheduler) as store:
            snapshot = _authorized_snapshot(store, snapshot_id)
            if snapshot.state != "ready" or snapshot.render_operation_id is None:
                raise ArchitectureHTTPError(404, "architecture artifact not found")
            artifact = store.scheduler.get_semantic_artifact(
                snapshot.render_operation_id, artifact_ref=snapshot.snapshot_id
            )
            render = artifact.render
            if render.binding_manifest is None or render.artifact_directory is None:
                raise C4BindingError("rendered snapshot has no hit-target manifest")
            workspace = _read_semantic_workspace(artifact)
            manifest = json.loads(render.binding_manifest.read_text(encoding="utf-8"))
            artifact_root = render.binding_manifest.parent.resolve()
            try:
                artifact_root.relative_to(render.artifact_directory.resolve())
            except ValueError as exc:
                raise C4BindingError("snapshot hit-target manifest escapes the render") from exc
            validate_hit_target_manifest(
                workspace=workspace,
                manifest=manifest,
                artifact_root=artifact_root,
                expected_view_keys=render.view_keys,
                expected_semantic_ids=artifact.contract.semantic_ids,
            )
            levels = _view_levels(workspace, render.view_keys)
            for row in manifest["views"]:
                key = row["view_key"]
                descriptor = {
                    "kind": "snapshot_svg",
                    "scope": snapshot.snapshot_id,
                    "render_identity": snapshot.descriptor["render"]["identity"],
                    "view_key": key,
                    "level": levels[key],
                }
                if _opaque_id(descriptor) == artifact_id:
                    body = _sanitize_svg(_semantic_svg(artifact_root, row))
                    if len(body) > MAX_SVG_BYTES:
                        raise ArchitectureHTTPError(413, "architecture SVG exceeds 4 MiB")
                    return body, _etag(body)
    except KeyError as exc:
        raise ArchitectureHTTPError(404, "architecture artifact not found") from exc
    except (C4BindingError, json.JSONDecodeError) as exc:
        raise ArchitectureHTTPError(409, str(exc)) from exc
    raise ArchitectureHTTPError(404, "architecture artifact not found")


def _snapshot_resource_bytes(
    root: Path,
    snapshot_id: str,
    resource_id: str,
    *,
    scheduler: C4RenderScheduler | None = None,
) -> tuple[bytes, str, str]:
    try:
        with ArchitectureSnapshotStore(project_for(root), root, scheduler=scheduler) as store:
            snapshot = _authorized_snapshot(store, snapshot_id)
            unit = _snapshot_associated_unit(store.project, snapshot)
            for descriptor in (
                *_snapshot_resource_descriptors(snapshot),
                *_snapshot_context_resource_descriptors(store.project, snapshot, unit),
            ):
                if _opaque_id(descriptor) != resource_id:
                    continue
                body = _read_descriptor_blob(store.project, descriptor)
                if descriptor.get("mode") == "section":
                    body = _markdown_section(body, str(descriptor["section"]))
                if len(body) > MAX_RESOURCE_BYTES:
                    raise ArchitectureHTTPError(413, "architecture resource exceeds 1 MiB")
                suffix = Path(str(descriptor["path"])).suffix.lower()
                content_type = {
                    ".json": "application/json; charset=utf-8",
                    ".dsl": "text/plain; charset=utf-8",
                    ".md": "text/markdown; charset=utf-8",
                }.get(suffix, "text/plain; charset=utf-8")
                return body, content_type, _etag(body)
    except KeyError as exc:
        raise ArchitectureHTTPError(404, "architecture resource not found") from exc
    raise ArchitectureHTTPError(404, "architecture resource not found")


def _resolve(root: Path, work_id: str) -> C4ReviewPayload:
    project = project_for(root)
    store = ArchitectureReviewStore(project)
    units = [unit for unit in store.units_affecting(work_id) if unit.owner_work_id == work_id]
    if not units:
        actor = "epic_architect" if work_id.startswith("epic_") else "feature_architect"
        lineage = f"epic:{work_id}" if work_id.startswith("epic_") else _lineage_from_ledger(root, work_id)
        return resolve_c4_review_payload(
            project, owner=actor, work_id=work_id, lineage=lineage, store=store
        )
    return _resolve_unit(root, units[-1])


def _resolve_unit(root: Path, unit: ArchitectureReviewUnit) -> C4ReviewPayload:
    return resolve_c4_review_payload(
        project_for(root), owner=unit.authorized_owner, work_id=unit.owner_work_id,
        lineage=unit.integration_lineage,
        lineage_revision=review_lineage_revision(project_for(root), unit.owner_work_id),
    )


def _publication_unit_for_scope(
    root: Path, scope: str, *, work_id: str | None = None,
) -> ArchitectureReviewUnit | None:
    """Resolve read-only design evidence from a durable publication descriptor."""
    if not scope or len(scope) > 160:
        return None
    path = project_for(root).target.root / ".cascade" / "architecture-publications.json"
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if ledger.get("version") != 1 or not isinstance(ledger.get("operations"), dict):
        raise ArchitectureHTTPError(409, "architecture publication ledger is invalid")
    for row in ledger["operations"].values():
        unit = ArchitectureReviewUnit.from_dict(row["proposal"])
        if unit.review_unit_id == scope:
            if work_id is not None and unit.owner_work_id != work_id:
                raise ArchitectureHTTPError(403, "architecture scope is not authorized for this work")
            return unit
    return None


def _unit_for_scope(root: Path, scope: str, *, work_id: str | None = None) -> ArchitectureReviewUnit:
    if not scope or len(scope) > 160:
        raise ArchitectureHTTPError(404, "architecture scope not found")
    unit = ArchitectureReviewStore(project_for(root)).get(scope)
    if unit is None or unit.review_unit_id != scope:
        raise ArchitectureHTTPError(404, "architecture scope not found")
    if work_id is not None and unit.owner_work_id != work_id:
        raise ArchitectureHTTPError(403, "architecture scope is not authorized for this work")
    return unit


def _lineage_from_ledger(root: Path, work_id: str) -> str:
    path = root / ".cascade" / "architecture-publications.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        rows = value.get("operations", {}).values()
        matches = [ArchitectureReviewUnit.from_dict(row["proposal"]) for row in rows]
        matches = [unit for unit in matches if unit.owner_work_id == work_id]
        if matches:
            return matches[-1].integration_lineage
    except (OSError, ValueError, TypeError, KeyError, WorkspaceError):
        pass
    return f"epic:{work_id}"


def _resource_descriptors(unit: ArchitectureReviewUnit) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = [{
        "kind": "plan", "side": "proposed", "scope": unit.review_unit_id,
        "repository_role": unit.plan.repository_role,
        "repository_key": unit.plan.repository_key, "revision": unit.plan.revision,
        "path": unit.plan.path.as_posix(), "digest": unit.plan.content_digest,
    }]

    def add_artifact(kind: str, side: str, artifact: Any) -> None:
        ref = artifact.reference
        rows.append({
            "kind": kind, "side": side, "scope": unit.review_unit_id,
            "repository_role": ref.destination_repository_role,
            "repository_key": ref.destination_repository_key,
            "target_repository_key": ref.target_repository_key,
            "revision": ref.revision, "path": ref.repository_path.as_posix(),
            "digest": artifact.content_digest,
        })

    add_artifact("design", "proposed", unit.design)
    if unit.accepted_baseline.model is not None:
        model = unit.accepted_baseline.model
        add_artifact("model", "current", model.contract)
        for artifact in model.sources:
            add_artifact("source", "current", artifact)
    if unit.proposed_model is not None:
        add_artifact("model", "proposed", unit.proposed_model.contract)
        for artifact in unit.proposed_model.sources:
            add_artifact("source", "proposed", artifact)
    return rows


def _all_resource_descriptors(
    root: Path, unit: ArchitectureReviewUnit
) -> list[dict[str, str]]:
    rows = _resource_descriptors(unit)
    baseline = None
    baseline_id = unit.accepted_baseline.accepted_review_unit_id
    if baseline_id:
        baseline = ArchitectureReviewStore(project_for(root)).get(baseline_id)

    def diff(kind: str, proposed: dict[str, str], current: dict[str, str] | None) -> None:
        row = {**proposed, "kind": f"{kind}_diff", "mode": "diff"}
        row.update({
            "before_revision": current["revision"] if current else "",
            "before_path": current["path"] if current else "",
            "before_digest": current["digest"] if current else "",
            "before_repository_role": current["repository_role"] if current else proposed["repository_role"],
            "before_repository_key": current["repository_key"] if current else proposed["repository_key"],
        })
        rows.append(row)

    by_key = {(row["kind"], row.get("side"), row["path"]): row for row in rows}
    proposed_plan = by_key[("plan", "proposed", unit.plan.path.as_posix())]
    current_plan = None
    if baseline is not None:
        current_plan = _resource_descriptors(baseline)[0]
    diff("plan", proposed_plan, current_plan)

    proposed_design = next(row for row in rows if row["kind"] == "design")
    current_design = None
    if baseline is not None:
        current_design = next(
            row for row in _resource_descriptors(baseline) if row["kind"] == "design"
        )
    else:
        # Without an accepted design, show the proposal commit's actual Git
        # change rather than presenting the entire existing file as an addition.
        repository = _repository(project_for(root), proposed_design)
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", f"{proposed_design['revision']}^"],
            cwd=repository.root, capture_output=True, text=True, check=False,
        )
        if parent.returncode == 0:
            descriptor = {**proposed_design, "revision": parent.stdout.strip(), "digest": None}
            try:
                before = _read_descriptor_blob(project_for(root), descriptor)
            except ArchitectureHTTPError as exc:
                if exc.status != 410:
                    raise
            else:
                current_design = {**descriptor, "digest": hashlib.sha256(before).hexdigest()}
    diff("design", proposed_design, current_design)
    rows[-1]["baseline_kind"] = "accepted_design" if baseline else "proposal_parent"

    proposed_model = [
        row for row in rows
        if row["side"] == "proposed" and row["kind"] in {"model", "source"}
    ]
    current_model = {
        row["path"]: row for row in rows
        if row["side"] == "current" and row["kind"] in {"model", "source"}
    }
    for proposed in proposed_model:
        diff(proposed["kind"], proposed, current_model.get(proposed["path"]))
    return rows


def _published_design_descriptors(root: Path, unit: ArchitectureReviewUnit) -> list[dict[str, str]]:
    return [row for row in _all_resource_descriptors(root, unit) if row["kind"] in {"design", "design_diff"}]


def _read_descriptor_blob(
    project: ProjectContext, descriptor: dict[str, object]
) -> bytes:
    repository = _repository(project, descriptor)
    object_name = f"{descriptor['revision']}:{descriptor['path']}"
    sized = subprocess.run(
        ["git", "cat-file", "-s", object_name],
        cwd=repository.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=False,
    )
    if sized.returncode != 0:
        raise ArchitectureHTTPError(410, "pinned architecture resource is unavailable")
    try:
        size = int(sized.stdout.strip())
    except ValueError as exc:
        raise ArchitectureHTTPError(409, "pinned architecture resource size is invalid") from exc
    if size > MAX_RESOURCE_BYTES:
        raise ArchitectureHTTPError(413, "architecture resource exceeds 1 MiB")
    result = subprocess.run(
        ["git", "show", object_name],
        cwd=repository.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ArchitectureHTTPError(410, "pinned architecture resource is unavailable")
    body = result.stdout
    digest = descriptor.get("digest")
    expected = str(digest).removeprefix("sha256:") if digest else None
    if expected is not None and hashlib.sha256(body).hexdigest() != expected:
        raise ArchitectureHTTPError(409, "pinned architecture resource digest mismatch")
    return body


def _repository(project: ProjectContext, descriptor: dict[str, object]) -> RepositoryContext:
    role = descriptor["repository_role"]
    repository = project.target if role == "target" else project.tracking
    expected = repository.repository_key
    if "target_repository_key" in descriptor and role == "target":
        expected = project.target_repository_key
    if descriptor["repository_key"] != expected:
        raise ArchitectureHTTPError(409, "pinned repository identity changed")
    return repository


def _markdown_section(body: bytes, section: str) -> bytes:
    """Extract one identifier-bearing Markdown block without rendering HTML."""

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchitectureHTTPError(409, "pinned Markdown resource is not UTF-8") from exc
    lines = text.splitlines(keepends=True)
    token = re.compile(r"(?<![A-Za-z0-9_.:-])" + re.escape(section) + r"(?![A-Za-z0-9_.:-])")
    start = next((index for index, line in enumerate(lines) if token.search(line)), None)
    if start is None:
        raise ArchitectureHTTPError(410, "pinned source section is unavailable")
    heading = re.match(r"^(#{1,6})\s", lines[start])
    if heading:
        level = len(heading.group(1))
        end = next(
            (
                index for index in range(start + 1, len(lines))
                if (match := re.match(r"^(#{1,6})\s", lines[index]))
                and len(match.group(1)) <= level
            ),
            len(lines),
        )
    elif item := re.match(r"^(\s*)(?:[-+*]|\d+[.)])\s", lines[start]):
        indentation = len(item.group(1))
        end = start + 1
        while end < len(lines):
            peer = re.match(r"^(\s*)(?:[-+*]|\d+[.)])\s", lines[end])
            if peer and len(peer.group(1)) <= indentation:
                break
            if re.match(r"^#{1,6}\s", lines[end]):
                break
            end += 1
    else:
        end = start + 1
        while end < len(lines) and lines[end].strip():
            if re.match(r"^#{1,6}\s", lines[end]):
                break
            end += 1
    return "".join(lines[start:end]).encode("utf-8")


def _opaque_id(value: dict[str, object]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest() + '"'


def _sanitize_svg(raw: str) -> bytes:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ArchitectureHTTPError(409, "validated architecture SVG is malformed") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ArchitectureHTTPError(409, "validated architecture artifact is not SVG")
    forbidden = {"script", "foreignobject", "iframe", "object", "embed"}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() in forbidden:
            raise ArchitectureHTTPError(409, "validated architecture SVG is unsafe")
        for name, value in node.attrib.items():
            local = name.rsplit("}", 1)[-1].lower()
            if local.startswith("on") or (
                local == "href" and str(value).strip().lower().startswith(("javascript:", "data:"))
            ):
                raise ArchitectureHTTPError(409, "validated architecture SVG is unsafe")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
