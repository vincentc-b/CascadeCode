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
from cascade.workspace.types import ProjectContext, RepositoryContext

MAX_METADATA_BYTES = 256 * 1024
MAX_SVG_BYTES = 4 * 1024 * 1024
MAX_RESOURCE_BYTES = 1024 * 1024


class ArchitectureHTTPError(WorkspaceError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


def project_for(root: Path) -> ProjectContext:
    return get_project_context() or ProjectContext.colocated(root)


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

    return _resolve(root, work_id)


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


def artifact_bytes(root: Path, scope: str, artifact_id: str) -> tuple[bytes, str]:
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


def resource_bytes(root: Path, scope: str, resource_id: str) -> tuple[bytes, str, str]:
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
