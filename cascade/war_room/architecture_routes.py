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
    value["approval_context"] = (
        _approval_context(root, payload).to_dict()
        if payload.review_unit_id else None
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
    if scope:
        unit = _unit_for_scope(root, scope, work_id=work_id)
        resources = _all_resource_descriptors(root, unit)
    value["resources"] = [
        {
            "kind": row["kind"], "side": row.get("side"), "path": row["path"],
            "revision": row["revision"],
            "url": f"/api/architecture/resources/{scope}/{_opaque_id(row)}",
        }
        for row in resources
    ]
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


def _approval_context(root: Path, payload: C4ReviewPayload) -> ReviewApprovalContext:
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
    unit = _unit_for_scope(root, scope)
    for descriptor in _all_resource_descriptors(root, unit):
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
            )).encode("utf-8")
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
            for descriptor in _snapshot_resource_descriptors(snapshot):
                if _opaque_id(descriptor) != resource_id:
                    continue
                body = _read_descriptor_blob(store.project, descriptor)
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
    )


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
    diff("design", proposed_design, current_design)

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


def _read_descriptor_blob(
    project: ProjectContext, descriptor: dict[str, str]
) -> bytes:
    repository = _repository(project, descriptor)
    result = subprocess.run(
        ["git", "show", f"{descriptor['revision']}:{descriptor['path']}"],
        cwd=repository.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ArchitectureHTTPError(410, "pinned architecture resource is unavailable")
    body = result.stdout
    expected = str(descriptor["digest"]).removeprefix("sha256:")
    if hashlib.sha256(body).hexdigest() != expected:
        raise ArchitectureHTTPError(409, "pinned architecture resource digest mismatch")
    return body


def _repository(project: ProjectContext, descriptor: dict[str, str]) -> RepositoryContext:
    role = descriptor["repository_role"]
    repository = project.target if role == "target" else project.tracking
    expected = repository.repository_key
    if "target_repository_key" in descriptor and role == "target":
        expected = project.target_repository_key
    if descriptor["repository_key"] != expected:
        raise ArchitectureHTTPError(409, "pinned repository identity changed")
    return repository


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
