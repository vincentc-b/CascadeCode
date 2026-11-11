"""Owner-scoped, revision-pinned data for paired C4 review clients."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from cascade.workspace.architecture_review import (
    AcceptedLineage,
    ArchitectureProposalError,
    ArchitectureReviewRecord,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PromotionJournal,
    read_architecture_state,
)
from cascade.workspace.c4_bindings import C4BindingError, validate_hit_target_manifest
from cascade.workspace.c4_diff import C4SemanticDiff, C4SemanticModelArtifact
from cascade.workspace.c4_scheduler import (
    C4RenderAdmissionError,
    C4RenderScheduler,
)
from cascade.workspace.c4_render import C4RenderArtifact
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext


ReviewPayloadState = Literal[
    "pending", "ready", "no_diagram_change", "empty_baseline",
    "missing_model", "missing_review", "unsupported_model", "render_failed",
    "invalid_artifact", "stale_revision", "partial_acceptance", "unavailable",
    # Backwards-compatible direct-composer states. Store-backed resolution
    # normalizes these before they reach the HTTP slice.
    "unchanged", "first", "empty", "removed", "error",
]


@dataclass(frozen=True)
class C4ReviewTarget:
    kind: Literal["element", "relationship"]
    semantic_id: str
    label: str = ""
    state: str = "unchanged"
    current: str = "absent"
    proposed: str = "absent"
    source: str | None = None
    destination: str | None = None
    drill_choices: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class C4ReviewSide:
    repository_key: str
    revision: str
    svg: str
    targets: tuple[C4ReviewTarget, ...]


@dataclass(frozen=True)
class C4ReviewView:
    key: str
    level: str
    state: str
    current: C4ReviewSide | None
    proposed: C4ReviewSide | None
    current_state: str = "absent"
    proposed_state: str = "absent"


@dataclass(frozen=True)
class C4ReviewPayload:
    """Serializable review data; errors remain useful and always name the diff."""

    state: ReviewPayloadState
    owner_work_id: str
    authorized_owner: str
    review_unit_id: str
    reviewed_tuple_digest: str
    repositories: tuple[dict[str, str], ...]
    views: tuple[C4ReviewView, ...]
    changed_views: tuple[tuple[str, str], ...]
    legend: tuple[dict[str, str], ...]
    summary: str
    requirements: tuple[str, ...]
    decisions: tuple[str, ...]
    diffs: dict[str, object]
    provenance: dict[str, object] | None = None
    targets: tuple[C4ReviewTarget, ...] = ()
    reason_code: str | None = None
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _LoadedView:
    key: str
    level: str
    side: C4ReviewSide


@dataclass(frozen=True)
class _SemanticTarget:
    kind: Literal["element", "relationship"]
    semantic_id: str
    label: str
    parent: str | None = None
    source: str | None = None
    destination: str | None = None


_LEGEND = (
    {"state": "added", "meaning": "present only in proposed"},
    {"state": "removed", "meaning": "present only in current"},
    {"state": "changed", "meaning": "semantic content changed"},
    {"state": "unchanged", "meaning": "no semantic change"},
)


def compose_c4_review_payload(
    unit: ArchitectureReviewUnit,
    diff: C4SemanticDiff,
    *,
    owner: str,
    work_id: str,
    current: C4SemanticModelArtifact | None,
    proposed: C4SemanticModelArtifact | None,
    plan_diff_reference: str,
) -> C4ReviewPayload:
    """Compose one exact review unit without heuristic artifact matching.

    View identity is the typed semantic-workspace collection plus its stable key.
    Labels, coordinates, list position, export IDs, and transient SVG IDs are never
    considered.  Artifact validation failures are returned as visible error data.
    """

    if owner != unit.authorized_owner or work_id != unit.owner_work_id:
        raise WorkspaceError("architecture review payload is outside the requested owner scope")
    if not plan_diff_reference.strip():
        raise ValueError("plan_diff_reference must be nonempty")

    base_diffs: dict[str, object] = {
        "source": diff.source_diff_reference,
        "model": _model_diff(diff),
        "plan": plan_diff_reference,
    }
    common = {
        "owner_work_id": unit.owner_work_id,
        "authorized_owner": unit.authorized_owner,
        "review_unit_id": unit.review_unit_id,
        "reviewed_tuple_digest": unit.reviewed_tuple_digest,
        "legend": _LEGEND,
        "summary": diff.summary,
        "requirements": unit.requirement_citations,
        "decisions": unit.decision_citations,
        "diffs": base_diffs,
        "provenance": _unit_provenance(unit),
    }

    if getattr(unit, "architecture_impact", "diagram_change") == "no_diagram_change":
        if (
            diff.state != "unchanged" or diff.identities or diff.containment
            or diff.views or diff.changed_view_keys or current is not None
            or proposed is not None or unit.proposed_model is not None
        ):
            return C4ReviewPayload(
                state="invalid_artifact", repositories=(), views=(), changed_views=(),
                reason_code="invalid_artifact",
                reason="no-diagram-change declaration contains model evidence",
                error="no-diagram-change declaration contains model evidence",
                **common,
            )
        return C4ReviewPayload(
            state="no_diagram_change", repositories=(), views=(), changed_views=(),
            reason_code="no_diagram_change", reason=unit.impact_reason,
            error=None, **common,
        )

    try:
        _validate_diff_artifacts(diff, current, proposed)
        if diff.state == "render_error":
            raise C4BindingError(diff.error or diff.summary)
        if (
            proposed is not None
            and proposed.render.status == "ready"
            and proposed.render.source_diff_reference != diff.source_diff_reference
        ):
            raise C4BindingError("proposed render and semantic diff name different source diffs")
        current_views, current_repo, current_targets = _load_side(
            unit, current, proposed_side=False
        )
        proposed_views, proposed_repo, proposed_targets = _load_side(
            unit, proposed, proposed_side=True
        )
        keyed_current = {(item.key, item.level): item for item in current_views}
        keyed_proposed = {(item.key, item.level): item for item in proposed_views}
        identities = sorted(set(keyed_current) | set(keyed_proposed))
        changed_keys = set(diff.changed_view_keys)
        target_inventory = _review_targets(
            current_targets, proposed_targets, diff, keyed_current, keyed_proposed
        )
        target_by_id = {target.semantic_id: target for target in target_inventory}
        views = tuple(
            C4ReviewView(
                key=key,
                level=level,
                state=_view_state(key, keyed_current.get((key, level)),
                                  keyed_proposed.get((key, level)), diff),
                current=_decorate_side(keyed_current[(key, level)].side, target_by_id)
                if (key, level) in keyed_current else None,
                proposed=_decorate_side(keyed_proposed[(key, level)].side, target_by_id)
                if (key, level) in keyed_proposed else None,
                current_state="present" if (key, level) in keyed_current else "absent",
                proposed_state=(
                    "present" if (key, level) in keyed_proposed else
                    "removed" if (key, level) in keyed_current else "absent"
                ),
            )
            for key, level in identities
        )
        changed = tuple((view.key, view.level) for view in views if view.key in changed_keys)
        represented = {key for key, _ in changed}
        missing = changed_keys - represented
        if missing:
            raise C4BindingError(
                f"changed view inventory has no exact artifact binding: {sorted(missing)}"
            )
        repositories = tuple(
            row for row in (current_repo, proposed_repo) if row is not None
        )
        return C4ReviewPayload(
            state=_payload_state(diff), repositories=repositories, views=views,
            changed_views=changed, targets=target_inventory, error=None, **common,
        )
    except (C4BindingError, OSError, ValueError, json.JSONDecodeError) as exc:
        # Failure data deliberately retains the source/model/plan diffs.  A
        # consumer must never substitute a static render or guess a pairing.
        return C4ReviewPayload(
            state="error", repositories=(), views=(), changed_views=(),
            error=str(exc), **common,
        )


def resolve_c4_review_payload(
    project: ProjectContext,
    *,
    owner: str,
    work_id: str,
    lineage: str,
    lineage_revision: str | None = None,
    store: ArchitectureReviewStore | None = None,
    scheduler: C4RenderScheduler | None = None,
) -> C4ReviewPayload:
    """Resolve the one authorized current review into a bounded projection.

    The canonical review store and accepted integration lineage select the tuple.
    Completed durable renders are read without admitting or running work. Every
    non-ready state retains an actionable reason and whatever pinned provenance
    is safely available to the authenticated owner.
    """

    review_store = store or ArchitectureReviewStore(project)
    hold = review_store.acceptance_hold(work_id)
    try:
        state = read_architecture_state(
            project,
            owner=owner,
            work_id=work_id,
            lineage=lineage,
            store=review_store,
            lineage_revision=lineage_revision,
        )
    except ArchitectureProposalError as exc:
        if exc.code not in {"stale_baseline", "artifact_changed", "destination_changed"}:
            raise
        return _state_payload(
            "stale_revision", owner, work_id, "stale_revision",
            str(exc).partition(": ")[2] or str(exc),
        )
    unit = state.unit
    try:
        publication = _current_publication(project, owner, work_id, lineage)
    except (OSError, ValueError, WorkspaceError) as exc:
        return _state_payload(
            "unavailable", owner, work_id, "unavailable", str(exc),
            unit=unit, accepted=state.accepted,
        )
    if publication is not None and (
        unit is None or publication["proposal"].review_unit_id != unit.review_unit_id
    ):
        published_unit = publication["proposal"]
        status = publication["status"]
        reason_code = publication.get("reason_code")
        message = publication.get("message") or "architecture publication is unavailable"
        mapped = _publication_payload_state(status, reason_code)
        return _state_payload(
            mapped, owner, work_id, str(reason_code or mapped), str(message),
            unit=published_unit, accepted=state.accepted,
        )
    if state.pending_promotion is not None:
        return _state_payload(
            "partial_acceptance", owner, work_id,
            "partial_acceptance",
            _promotion_reason(state.pending_promotion),
            unit=unit, accepted=state.accepted, promotion=state.pending_promotion,
        )
    if hold is not None:
        return _state_payload(
            "pending", owner, work_id, "pending",
            f"architecture publication {hold} is still validating bounded render evidence",
            unit=unit, accepted=state.accepted,
        )
    if unit is None:
        return _state_payload(
            "missing_review", owner, work_id, "missing_review",
            "no architecture review is published for this owner and integration lineage",
            accepted=state.accepted,
        )
    provenance = _unit_provenance(unit, state.accepted, state.review, None)
    if unit.status == "stale" or state.invalidation_reasons:
        detail = ", ".join(state.invalidation_reasons) or "accepted baseline changed"
        return _state_payload(
            "stale_revision", owner, work_id, "stale_revision",
            f"review must be republished at current revisions: {detail}",
            unit=unit, accepted=state.accepted, review=state.review,
        )
    if unit.status in {"reviewed", "approved", "rejected"} and state.review is None:
        return _state_payload(
            "missing_review", owner, work_id, "missing_review",
            "review status has no matching immutable review decision",
            unit=unit, accepted=state.accepted,
        )
    diff = state.semantic_diff
    if diff is None:
        code = "missing_model" if unit.architecture_impact == "diagram_change" else "pending"
        return _state_payload(
            code, owner, work_id, code,
            "published tuple is waiting for its validated semantic diff",
            unit=unit, accepted=state.accepted, review=state.review,
        )
    if diff.state == "render_error":
        return _state_payload(
            "render_failed", owner, work_id, "render_failed",
            diff.error or diff.summary,
            unit=unit, accepted=state.accepted, review=state.review,
        )
    plan_diff = _plan_diff_reference(review_store, unit, state.accepted)
    if unit.architecture_impact == "no_diagram_change":
        payload = compose_c4_review_payload(
            unit, diff, owner=owner, work_id=work_id,
            current=None, proposed=None, plan_diff_reference=plan_diff,
        )
        return replace(
            payload,
            provenance=provenance,
            reason_code="no_diagram_change",
            reason=unit.impact_reason,
        )
    if unit.proposed_model is None:
        return _state_payload(
            "missing_model", owner, work_id, "missing_model",
            "diagram change has no pinned proposed model",
            unit=unit, accepted=state.accepted, review=state.review,
        )
    if unit.proposed_model.render_identity is None:
        return _state_payload(
            "unsupported_model", owner, work_id, "unsupported_model",
            "pinned model predates durable render identity and must be republished",
            unit=unit, accepted=state.accepted, review=state.review,
        )

    owned_scheduler = scheduler is None
    render_scheduler = scheduler or C4RenderScheduler(
        project.target.root, start_worker=False
    )
    try:
        proposed = _scheduled_artifact(render_scheduler, unit.proposed_model, unit.review_unit_id)
        current = None
        if unit.accepted_baseline.kind == "model":
            binding = unit.accepted_baseline.model
            if binding is None or binding.render_identity is None:
                return _state_payload(
                    "unsupported_model", owner, work_id, "unsupported_model",
                    "accepted baseline predates durable render identity",
                    unit=unit, accepted=state.accepted, review=state.review,
                )
            current = _scheduled_artifact(
                render_scheduler,
                binding,
                unit.accepted_baseline.accepted_review_unit_id or "accepted-baseline",
            )
        elif diff.current_artifact_ref is not None:
            current = C4SemanticModelArtifact(
                diff.current_artifact_ref,
                C4RenderArtifact(status="empty", closure_digest="empty_baseline"),
                proposed.contract,
            )
        payload = compose_c4_review_payload(
            unit, diff, owner=owner, work_id=work_id,
            current=current, proposed=proposed, plan_diff_reference=plan_diff,
        )
    except KeyError:
        return _state_payload(
            "missing_model", owner, work_id, "missing_model",
            "pinned durable render operation is missing",
            unit=unit, accepted=state.accepted, review=state.review,
        )
    except C4RenderAdmissionError as exc:
        mapped_state: ReviewPayloadState = {
            "artifact_pending": "pending",
            "validation_failed": "unsupported_model",
            "binding_failed": "unsupported_model",
            "invalid_artifact": "invalid_artifact",
        }.get(exc.code, "render_failed")
        return _state_payload(
            mapped_state, owner, work_id, exc.code,
            str(exc).partition(": ")[2] or str(exc),
            unit=unit, accepted=state.accepted, review=state.review,
        )
    except RuntimeError as exc:
        return _state_payload(
            "unavailable", owner, work_id, "unavailable", str(exc),
            unit=unit, accepted=state.accepted, review=state.review,
        )
    except (OSError, ValueError, WorkspaceError) as exc:
        return _state_payload(
            "invalid_artifact", owner, work_id, "invalid_artifact", str(exc),
            unit=unit, accepted=state.accepted, review=state.review,
        )
    finally:
        if owned_scheduler:
            render_scheduler.close()

    if payload.state == "error":
        return replace(
            payload,
            state="invalid_artifact",
            provenance=provenance,
            reason_code="invalid_artifact",
            reason=payload.error or "review artifact validation failed",
        )
    normalized = "empty_baseline" if diff.state in {"first_model", "empty_baseline"} else "ready"
    return replace(
        payload,
        state=normalized,
        provenance=provenance,
        reason_code=normalized,
        reason=(
            "validated proposal is compared with an explicit empty baseline"
            if normalized == "empty_baseline" else
            "validated revision-pinned architecture review is ready"
        ),
    )


def _load_side(
    unit: ArchitectureReviewUnit,
    artifact: C4SemanticModelArtifact | None,
    *,
    proposed_side: bool,
) -> tuple[
    tuple[_LoadedView, ...], dict[str, str] | None, dict[str, _SemanticTarget]
]:
    binding = unit.proposed_model if proposed_side else unit.accepted_baseline.model
    if artifact is None:
        if binding is not None:
            raise C4BindingError("pinned model has no corresponding rendered artifact")
        return (), None, {}
    if binding is None:
        if artifact.render.status in {"first", "empty"}:
            return (), None, {}
        raise C4BindingError("rendered artifact has no pinned model binding")
    reference = binding.contract.reference
    render = artifact.render
    if render.status in {"first", "empty"}:
        if render.revision is not None and render.revision != reference.revision:
            raise C4BindingError("empty render does not match its pinned revision")
        return (), {
            "side": "proposed" if proposed_side else "current",
            "repository_key": reference.destination_repository_key,
            "revision": reference.revision,
        }, {}
    if render.status != "ready" or not render.interactive:
        raise C4BindingError(f"rendered artifact is not interactively reviewable: {render.status}")
    if render.revision != reference.revision:
        raise C4BindingError(
            f"render revision {render.revision!r} does not match pinned revision "
            f"{reference.revision!r}"
        )
    if render.binding_manifest is None or render.artifact_directory is None:
        raise C4BindingError("rendered artifact has no hit-target manifest")
    artifact_root = render.binding_manifest.parent.resolve()
    try:
        artifact_root.relative_to(render.artifact_directory.resolve())
    except ValueError as exc:
        raise C4BindingError("hit-target manifest escapes the rendered artifact") from exc
    workspace = _read_semantic_workspace(artifact)
    inventory = _semantic_targets(workspace)
    manifest = json.loads(render.binding_manifest.read_text(encoding="utf-8"))
    validate_hit_target_manifest(
        workspace=workspace,
        manifest=manifest,
        artifact_root=artifact_root,
        expected_view_keys=render.view_keys,
        expected_semantic_ids=artifact.contract.semantic_ids,
    )
    levels = _view_levels(workspace, render.view_keys)
    manifest_rows = {row["view_key"]: row for row in manifest["views"]}
    result: list[_LoadedView] = []
    for key in render.view_keys:
        row = manifest_rows[key]
        targets = tuple(sorted(
            (
                C4ReviewTarget(target["kind"], target["semantic_id"])
                for target in row["targets"]
            ),
            key=lambda target: (target.kind, target.semantic_id),
        ))
        result.append(
            _LoadedView(
                key,
                levels[key],
                C4ReviewSide(
                    reference.destination_repository_key,
                    reference.revision,
                    _semantic_svg(artifact_root, row),
                    targets,
                ),
            )
        )
    repository = {
        "side": "proposed" if proposed_side else "current",
        "repository_key": reference.destination_repository_key,
        "revision": reference.revision,
    }
    return tuple(result), repository, inventory


def _semantic_targets(workspace: dict[str, object]) -> dict[str, _SemanticTarget]:
    model = workspace.get("model")
    if not isinstance(model, dict):
        raise C4BindingError("semantic workspace has no model inventory")
    rows: dict[str, tuple[dict[str, object], str | None]] = {}
    export_ids: dict[str, str] = {}

    def visit(value: object, parent: str | None = None) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item, parent)
            return
        if not isinstance(value, dict):
            return
        properties = value.get("properties")
        semantic_id = (
            properties.get("cascade.semanticId")
            if isinstance(properties, dict) else None
        )
        next_parent = parent
        if semantic_id is not None:
            if not isinstance(semantic_id, str) or not semantic_id or semantic_id in rows:
                raise C4BindingError("semantic workspace has duplicate or invalid identities")
            export_id = value.get("id")
            if not isinstance(export_id, (str, int)) or str(export_id) in export_ids:
                raise C4BindingError("semantic workspace has duplicate or invalid export IDs")
            rows[semantic_id] = (value, parent)
            export_ids[str(export_id)] = semantic_id
            if "sourceId" not in value and "destinationId" not in value:
                next_parent = semantic_id
        for key, child in value.items():
            if key != "properties":
                visit(child, next_parent)

    visit(model)
    result: dict[str, _SemanticTarget] = {}
    for semantic_id, (row, parent) in rows.items():
        relationship = "sourceId" in row or "destinationId" in row
        source = export_ids.get(str(row.get("sourceId"))) if relationship else None
        destination = export_ids.get(str(row.get("destinationId"))) if relationship else None
        if relationship and (source is None or destination is None):
            raise C4BindingError(
                f"relationship {semantic_id!r} has an invalid semantic endpoint"
            )
        raw_label = row.get("name") if not relationship else row.get("description")
        label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else semantic_id
        result[semantic_id] = _SemanticTarget(
            "relationship" if relationship else "element",
            semantic_id,
            label,
            parent,
            source,
            destination,
        )
    return result


def _decorate_side(
    side: C4ReviewSide, targets: dict[str, C4ReviewTarget]
) -> C4ReviewSide:
    return C4ReviewSide(
        side.repository_key,
        side.revision,
        side.svg,
        tuple(targets[item.semantic_id] for item in side.targets),
    )


def _review_targets(
    current: dict[str, _SemanticTarget],
    proposed: dict[str, _SemanticTarget],
    diff: C4SemanticDiff,
    current_views: dict[tuple[str, str], _LoadedView],
    proposed_views: dict[tuple[str, str], _LoadedView],
) -> tuple[C4ReviewTarget, ...]:
    changes = {item.semantic_id: item.state for item in diff.identities}
    view_identities = sorted(
        set(current_views) | set(proposed_views), key=lambda identity: (identity[1], identity[0])
    )
    memberships: dict[str, set[str]] = {}
    for view in diff.views:
        for semantic_id in (
            *view.current_elements, *view.proposed_elements,
            *view.current_relationships, *view.proposed_relationships,
        ):
            memberships.setdefault(semantic_id, set()).add(view.key)

    # A parent can drill into a view that explicitly contains one of its
    # descendants. Parent identity comes only from the validated semantic model.
    parents = {
        semantic_id: target.parent
        for semantic_id, target in {**current, **proposed}.items()
        if target.kind == "element"
    }
    for semantic_id, keys in tuple(memberships.items()):
        seen: set[str] = set()
        parent = parents.get(semantic_id)
        while parent is not None and parent not in seen:
            seen.add(parent)
            memberships.setdefault(parent, set()).update(keys)
            parent = parents.get(parent)

    result: list[C4ReviewTarget] = []
    for semantic_id in sorted(set(current) | set(proposed)):
        before = current.get(semantic_id)
        after = proposed.get(semantic_id)
        target = after or before
        assert target is not None
        state = changes.get(
            semantic_id,
            "added" if before is None else "removed" if after is None else "unchanged",
        )
        choices = tuple(
            {
                "view_key": key,
                "level": level,
                "label": f"{key} ({level})",
            }
            for key, level in view_identities
            if key in memberships.get(semantic_id, ())
        )
        result.append(C4ReviewTarget(
            target.kind,
            semantic_id,
            target.label,
            state,
            "present" if before is not None else "absent",
            "present" if after is not None else "removed" if before is not None else "absent",
            target.source,
            target.destination,
            choices,
        ))
    return tuple(result)


def _semantic_svg(artifact_root: Path, row: dict[str, object]) -> str:
    """Return the validated SVG with stable semantic hit-target annotations.

    Renderer node and export IDs remain an implementation detail of the pinned
    artifact.  The review client receives only the semantic identity proven by
    the same-render manifest validation above.
    """

    svg_path = artifact_root / str(row["svg"])
    tree = ET.parse(svg_path)
    nodes = {
        node.get("id"): node
        for node in tree.iter()
        if node.get("id") is not None
    }
    for target in row["targets"]:
        if not isinstance(target, dict):  # Already rejected by manifest validation.
            raise C4BindingError("hit-target manifest target is invalid")
        renderer_id = target["renderer_node_id"]
        node = nodes.get(renderer_id)
        if node is None:
            raise C4BindingError("validated SVG lost a hit-target node")
        node.set("data-cascade-semantic-id", str(target["semantic_id"]))
        node.set("data-cascade-model-kind", str(target["kind"]))
    return ET.tostring(tree.getroot(), encoding="unicode")


def _read_semantic_workspace(artifact: C4SemanticModelArtifact) -> dict[str, object]:
    path = artifact.render.semantic_workspace
    digest = artifact.render.semantic_workspace_sha256
    if path is None or digest is None:
        raise C4BindingError("rendered artifact has no pinned semantic workspace")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise C4BindingError("semantic workspace bytes changed after validation")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise C4BindingError("semantic workspace is not an object")
    return value


def _view_levels(
    workspace: dict[str, object], expected: tuple[str, ...]
) -> dict[str, str]:
    raw_views = workspace.get("views")
    if not isinstance(raw_views, dict):
        raise C4BindingError("semantic workspace has no view inventory")
    levels: dict[str, str] = {}
    for level, rows in raw_views.items():
        if not level.endswith("Views"):
            continue
        if not isinstance(rows, list):
            raise C4BindingError(f"semantic view level {level!r} is invalid")
        for row in rows:
            key = row.get("key") if isinstance(row, dict) else None
            if not isinstance(key, str) or not key or key in levels:
                raise C4BindingError("semantic workspace has an ambiguous view binding")
            levels[key] = level
    if set(levels) != set(expected):
        raise C4BindingError("semantic and rendered view inventories disagree")
    return levels


def _validate_diff_artifacts(
    diff: C4SemanticDiff,
    current: C4SemanticModelArtifact | None,
    proposed: C4SemanticModelArtifact | None,
) -> None:
    current_ref = current.artifact_ref if current else None
    proposed_ref = proposed.artifact_ref if proposed else None
    if diff.current_artifact_ref != current_ref or diff.proposed_artifact_ref != proposed_ref:
        raise C4BindingError("semantic diff does not name the supplied artifacts")


def _view_state(
    key: str,
    current: _LoadedView | None,
    proposed: _LoadedView | None,
    diff: C4SemanticDiff,
) -> str:
    if current is None:
        return "added"
    if proposed is None:
        return "removed"
    return next((view.state for view in diff.views if view.key == key), "unchanged")


def _payload_state(diff: C4SemanticDiff) -> ReviewPayloadState:
    return {
        "first_model": "first",
        "empty_baseline": "empty",
        "empty_proposal": "removed",
        "render_error": "error",
        "unchanged": "unchanged",
        "changed": "ready",
    }[diff.state]


def _model_diff(diff: C4SemanticDiff) -> dict[str, object]:
    return {
        "state": diff.state,
        "identities": [asdict(item) for item in diff.identities],
        "containment": [asdict(item) for item in diff.containment],
        "views": [asdict(item) for item in diff.views],
        "changed_view_keys": list(diff.changed_view_keys),
        "error": diff.error,
    }


def _scheduled_artifact(scheduler, binding, artifact_ref) -> C4SemanticModelArtifact:
    operation_id = f"c4-render-{binding.render_identity}"
    scheduled = scheduler.get(operation_id)
    if scheduled.status in {"pending", "running"}:
        raise C4RenderAdmissionError(
            "artifact_pending", f"render {operation_id} is {scheduled.status}"
        )
    if scheduled.status != "ready":
        failure = scheduled.failure
        raise C4RenderAdmissionError(
            failure.code if failure else "render_failed",
            failure.message if failure else f"render {operation_id} is {scheduled.status}",
        )
    artifact = scheduler.get_semantic_artifact(operation_id, artifact_ref=artifact_ref)
    render = artifact.render
    semantic = render.semantic_workspace
    if render.closure_digest != binding.source_closure_digest:
        raise C4BindingError("durable render closure differs from pinned model")
    if render.image_digest != binding.renderer_image_digest:
        raise C4BindingError("durable renderer image differs from pinned model")
    if semantic is None or not semantic.is_file():
        raise C4BindingError("durable render has no semantic workspace")
    digest = hashlib.sha256(semantic.read_bytes()).hexdigest()
    if digest != binding.semantic_artifact_digest or digest != render.semantic_workspace_sha256:
        raise C4BindingError("durable semantic workspace differs from pinned model")
    return artifact


def _plan_diff_reference(
    store: ArchitectureReviewStore,
    unit: ArchitectureReviewUnit,
    accepted: AcceptedLineage | None,
) -> str:
    baseline_revision = None
    baseline_id = unit.accepted_baseline.accepted_review_unit_id
    if baseline_id is not None:
        baseline_unit = store.get(baseline_id)
        if baseline_unit is not None:
            baseline_revision = baseline_unit.plan.revision
    if baseline_revision is None and accepted is not None:
        accepted_unit = store.get(accepted.accepted_review_unit_id)
        if accepted_unit is not None:
            baseline_revision = accepted_unit.plan.revision
    return (
        f"git:{baseline_revision}..{unit.plan.revision}"
        if baseline_revision is not None else f"git:empty..{unit.plan.revision}"
    )


def _unit_provenance(
    unit: ArchitectureReviewUnit,
    accepted: AcceptedLineage | None = None,
    review: ArchitectureReviewRecord | None = None,
    promotion: PromotionJournal | None = None,
) -> dict[str, object]:
    # Direct composer callers historically supplied a narrow unit-shaped test
    # double. Keep that API useful while the store-backed resolver always passes
    # the complete durable unit below.
    if not hasattr(unit, "status"):
        baseline_model = unit.accepted_baseline.model
        return {
            "review_unit_id": unit.review_unit_id,
            "reviewed_tuple_digest": unit.reviewed_tuple_digest,
            "documentation": {
                "proposed_model_revision": (
                    unit.proposed_model.contract.reference.revision
                    if unit.proposed_model is not None else None
                ),
                "baseline_model_revision": (
                    baseline_model.contract.reference.revision if baseline_model else None
                ),
            },
        }
    proposed_revision = (
        unit.proposed_model.contract.reference.revision
        if unit.proposed_model is not None else None
    )
    baseline_model = unit.accepted_baseline.model
    return {
        "review_unit_id": unit.review_unit_id,
        "reviewed_tuple_digest": unit.reviewed_tuple_digest,
        "review_status": unit.status,
        "integration_lineage": unit.integration_lineage,
        "plan": unit.plan.to_dict(),
        "design": {
            "repository_key": unit.design.reference.destination_repository_key,
            "repository_role": unit.design.reference.destination_repository_role,
            "path": unit.design.reference.repository_path.as_posix(),
            "revision": unit.design.reference.revision,
            "content_digest": unit.design.content_digest,
        },
        "code": {
            "repository_key": unit.code_repository_key,
            "accepted_revision": accepted.accepted_code_head if accepted else None,
        },
        "documentation": {
            "repository_key": unit.documentation_repository_key,
            "repository_role": unit.documentation_repository_role,
            "destination_path": unit.documentation_destination_path.as_posix(),
            "accepted_revision": accepted.accepted_documentation_head if accepted else None,
            "design_revision": unit.design.reference.revision,
            "proposed_model_revision": proposed_revision,
            "baseline_model_revision": (
                baseline_model.contract.reference.revision if baseline_model else None
            ),
        },
        "baseline": {
            "kind": unit.accepted_baseline.kind,
            "pointer_id": unit.baseline_pointer_id,
            "generation": unit.baseline_generation,
            "accepted_review_unit_id": unit.accepted_baseline.accepted_review_unit_id,
            "current_pointer_id": accepted.pointer_id if accepted else None,
            "current_generation": accepted.generation if accepted else None,
        },
        "review": review.to_dict() if review else None,
        "promotion": promotion.to_dict() if promotion else None,
    }


def _accepted_provenance(accepted: AcceptedLineage | None) -> dict[str, object]:
    if accepted is None:
        return {
            "accepted_lineage": None,
            "code": {"accepted_revision": None},
            "documentation": {"accepted_revision": None},
        }
    return {
        "accepted_lineage": {
            "lineage_key": accepted.lineage_key,
            "pointer_id": accepted.pointer_id,
            "generation": accepted.generation,
            "review_unit_id": accepted.accepted_review_unit_id,
            "tuple_digest": accepted.accepted_tuple_digest,
            "baseline_kind": accepted.baseline.kind,
        },
        "code": {"accepted_revision": accepted.accepted_code_head},
        "documentation": {
            "accepted_revision": accepted.accepted_documentation_head,
        },
    }


def _state_payload(
    state: ReviewPayloadState,
    owner: str,
    work_id: str,
    code: str,
    reason: str,
    *,
    unit: ArchitectureReviewUnit | None = None,
    accepted: AcceptedLineage | None = None,
    review: ArchitectureReviewRecord | None = None,
    promotion: PromotionJournal | None = None,
) -> C4ReviewPayload:
    provenance = (
        _unit_provenance(unit, accepted, review, promotion)
        if unit is not None else _accepted_provenance(accepted)
    )
    return C4ReviewPayload(
        state=state,
        owner_work_id=unit.owner_work_id if unit else work_id,
        authorized_owner=unit.authorized_owner if unit else owner,
        review_unit_id=unit.review_unit_id if unit else "",
        reviewed_tuple_digest=unit.reviewed_tuple_digest if unit else "",
        repositories=(),
        views=(),
        changed_views=(),
        legend=_LEGEND,
        summary=reason,
        requirements=unit.requirement_citations if unit else (),
        decisions=unit.decision_citations if unit else (),
        diffs={"source": None, "model": None, "plan": None},
        provenance=provenance,
        reason_code=code,
        reason=reason,
        error=reason if state not in {"pending", "no_diagram_change"} else None,
    )


def _promotion_reason(promotion: PromotionJournal) -> str:
    waiting = []
    if promotion.code.state != "landed":
        waiting.append("code")
    if promotion.documentation.state != "landed":
        waiting.append("documentation")
    suffix = " and ".join(waiting) if waiting else "lineage finalization"
    return f"partial acceptance is waiting for {suffix} at the pinned promotion revisions"


def _current_publication(
    project: ProjectContext, owner: str, work_id: str, lineage: str
) -> dict[str, object] | None:
    path = project.target.root / ".cascade" / "architecture-publications.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if (
        not isinstance(value, dict) or value.get("version") != 1
        or not isinstance(value.get("operations"), dict)
    ):
        raise ValueError("architecture publication ledger is invalid")
    matches: list[dict[str, object]] = []
    for row in value["operations"].values():
        if not isinstance(row, dict) or not isinstance(row.get("proposal"), dict):
            raise ValueError("architecture publication ledger is invalid")
        proposal = ArchitectureReviewUnit.from_dict(row["proposal"])
        if (
            proposal.authorized_owner == owner
            and proposal.owner_work_id == work_id
            and proposal.integration_lineage == lineage
        ):
            matches.append({**row, "proposal": proposal})
    if not matches:
        return None
    return max(
        matches,
        key=lambda row: (
            float(row.get("updated_at", 0)), str(row.get("operation_id", ""))
        ),
    )


def _publication_payload_state(status: object, reason_code: object) -> ReviewPayloadState:
    if status == "pending":
        return "pending"
    if status == "superseded" and reason_code in {
        "stale_revision", "stale_baseline", "artifact_changed", "destination_changed",
    }:
        return "stale_revision"
    if reason_code in {"model_required", "artifact_unavailable"}:
        return "missing_model"
    if reason_code in {"validation_failed", "binding_failed", "model_unsupported"}:
        return "unsupported_model"
    if reason_code in {"invalid_artifact", "invalid_publication", "model_invalid"}:
        return "invalid_artifact"
    if status == "failed":
        return "render_failed"
    return "unavailable"
