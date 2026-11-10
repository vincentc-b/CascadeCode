"""Semantic comparison of validated Structurizr render artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.workspace.c4_render import C4RenderArtifact
from cascade.workspace.c4_source import C4WorkspaceContract


DiffState = Literal[
    "changed",
    "unchanged",
    "first_model",
    "empty_baseline",
    "empty_proposal",
    "render_error",
]
ChangeState = Literal["added", "removed", "changed", "unchanged"]
ViewState = Literal[
    "added",
    "removed_view",
    "changed",
    "unchanged",
    "first_model",
    "empty_baseline",
    "empty_proposal",
    "render_error",
]

_SEMANTIC_ID = "cascade.semanticId"
_DSL_ID = "structurizr.dsl.identifier"
_MODEL_CHILD_KEYS = frozenset(
    {
        "people",
        "softwareSystems",
        "containers",
        "components",
        "deploymentNodes",
        "infrastructureNodes",
        "softwareSystemInstances",
        "containerInstances",
        "customElements",
        "relationships",
        "children",
    }
)
_VIEW_MEMBER_KEYS = frozenset({"elements", "relationships"})
_VIEW_LAYOUT_KEYS = frozenset(
    {
        "automaticLayout",
        "order",
        "paperSize",
        "dimensions",
        "animations",
        "defaultElementView",
    }
)
_VIEW_MODEL_SCOPE_IDS = frozenset({"softwareSystemId", "containerId", "elementId"})


@dataclass(frozen=True)
class C4SemanticModelArtifact:
    """A validated source contract joined to its immutable render result."""

    artifact_ref: str
    render: C4RenderArtifact
    contract: C4WorkspaceContract


@dataclass(frozen=True)
class C4IdentityChange:
    kind: Literal["element", "relationship"]
    semantic_id: str
    state: ChangeState
    previous_semantic_id: str | None = None
    changed_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class C4ContainmentChange:
    semantic_id: str
    current_parent: str | None
    proposed_parent: str | None


@dataclass(frozen=True)
class C4ViewDiff:
    key: str
    state: ViewState
    current_elements: tuple[str, ...] = ()
    proposed_elements: tuple[str, ...] = ()
    current_relationships: tuple[str, ...] = ()
    proposed_relationships: tuple[str, ...] = ()
    changed_identities: tuple[str, ...] = ()


@dataclass(frozen=True)
class C4SemanticDiff:
    """API-safe semantic delta for later review and interaction features."""

    state: DiffState
    current_artifact_ref: str | None
    proposed_artifact_ref: str | None
    source_diff_reference: str
    identities: tuple[C4IdentityChange, ...]
    containment: tuple[C4ContainmentChange, ...]
    views: tuple[C4ViewDiff, ...]
    changed_view_keys: tuple[str, ...]
    summary: str
    error: str | None = None


@dataclass(frozen=True)
class _Identity:
    kind: Literal["element", "relationship"]
    semantic_id: str
    properties: object
    parent: str | None
    source: str | None = None
    destination: str | None = None


@dataclass(frozen=True)
class _View:
    key: str
    properties: object
    elements: frozenset[str]
    relationships: frozenset[str]


@dataclass(frozen=True)
class _Model:
    identities: dict[str, _Identity]
    views: dict[str, _View]


class _DiffInputError(ValueError):
    pass


def compute_c4_semantic_diff(
    current: C4SemanticModelArtifact | None,
    proposed: C4SemanticModelArtifact | None,
    *,
    source_diff_reference: str,
) -> C4SemanticDiff:
    """Compare validated artifacts without labels, layout, order, or numeric IDs.

    Rename continuity is applied only from the proposal's reviewed source
    contract.  A missing baseline is distinct from a rendered empty baseline,
    and a missing or empty proposal is explicit rather than an unchanged diff.
    """

    if not source_diff_reference.strip():
        raise ValueError("source_diff_reference must be nonempty")

    current_ref = current.artifact_ref if current else None
    proposed_ref = proposed.artifact_ref if proposed else None
    current_status = current.render.status if current else "first"
    proposed_status = proposed.render.status if proposed else "empty"

    error = _render_error(current) or _render_error(proposed)
    if error:
        keys = sorted(
            set(current.render.view_keys if current else ())
            | set(proposed.render.view_keys if proposed else ())
        )
        return _state_diff(
            "render_error",
            current_ref,
            proposed_ref,
            source_diff_reference,
            keys,
            error,
        )
    if proposed is None or proposed_status == "empty":
        keys = sorted(current.render.view_keys if current else ())
        return _state_diff(
            "empty_proposal",
            current_ref,
            proposed_ref,
            source_diff_reference,
            keys,
        )

    initial_state: DiffState | None = None
    if current is None or current_status == "first":
        initial_state = "first_model"
    elif current_status == "empty":
        initial_state = "empty_baseline"

    try:
        proposed_model = _load_model(proposed)
        current_model = _Model({}, {}) if initial_state else _load_model(current)
        renames = _applicable_renames(current_model, proposed_model, proposed.contract)
        identities, containment = _compare_identities(
            current_model, proposed_model, renames
        )
        views = _compare_views(
            current_model,
            proposed_model,
            renames,
            identities,
            containment,
            initial_state,
        )
    except (OSError, json.JSONDecodeError, _DiffInputError) as exc:
        keys = sorted(
            set(current.render.view_keys if current else ())
            | set(proposed.render.view_keys)
        )
        return _state_diff(
            "render_error",
            current_ref,
            proposed_ref,
            source_diff_reference,
            keys,
            f"invalid semantic artifact identity: {exc}",
        )

    changed_views = tuple(view.key for view in views if view.state != "unchanged")
    changed_identities = sum(item.state != "unchanged" for item in identities)
    state = initial_state or (
        "changed" if changed_identities or containment or changed_views else "unchanged"
    )
    summary = (
        f"{state.replace('_', ' ')}: {changed_identities} identity change(s), "
        f"{len(containment)} containment change(s), "
        f"{len(changed_views)} affected view(s)"
    )
    return C4SemanticDiff(
        state=state,
        current_artifact_ref=current_ref,
        proposed_artifact_ref=proposed_ref,
        source_diff_reference=source_diff_reference,
        identities=identities,
        containment=containment,
        views=views,
        changed_view_keys=changed_views,
        summary=summary,
    )


def _render_error(artifact: C4SemanticModelArtifact | None) -> str | None:
    if artifact is None or artifact.render.status in {"first", "empty", "ready"}:
        return None
    failure = artifact.render.failure
    if failure:
        return f"{artifact.artifact_ref}: {failure.stage}: {failure.message}"
    return f"{artifact.artifact_ref}: render is {artifact.render.status}"


def _state_diff(
    state: DiffState,
    current_ref: str | None,
    proposed_ref: str | None,
    source_diff_reference: str,
    keys: list[str],
    error: str | None = None,
) -> C4SemanticDiff:
    view_state: ViewState = state  # type: ignore[assignment]
    views = tuple(C4ViewDiff(key=key, state=view_state) for key in keys)
    summary = error or state.replace("_", " ")
    return C4SemanticDiff(
        state=state,
        current_artifact_ref=current_ref,
        proposed_artifact_ref=proposed_ref,
        source_diff_reference=source_diff_reference,
        identities=(),
        containment=(),
        views=views,
        changed_view_keys=tuple(keys),
        summary=summary,
        error=error,
    )


def _load_model(artifact: C4SemanticModelArtifact | None) -> _Model:
    if artifact is None or artifact.render.semantic_workspace is None:
        raise _DiffInputError("ready artifact has no semantic workspace")
    workspace_bytes = Path(artifact.render.semantic_workspace).read_bytes()
    expected_hash = artifact.render.semantic_workspace_sha256
    if not expected_hash:
        raise _DiffInputError("ready artifact has no verified semantic workspace digest")
    if hashlib.sha256(workspace_bytes).hexdigest() != expected_hash:
        raise _DiffInputError("semantic workspace bytes changed after render validation")
    payload = json.loads(workspace_bytes)
    if not isinstance(payload, dict) or not isinstance(payload.get("model"), dict):
        raise _DiffInputError("workspace JSON has no model object")

    raw: dict[str, tuple[dict[str, object], str | None]] = {}
    export_ids: dict[str, str] = {}

    def visit(value: object, parent: str | None = None) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child, parent)
            return
        if not isinstance(value, dict):
            return
        properties = value.get("properties")
        semantic_id = properties.get(_SEMANTIC_ID) if isinstance(properties, dict) else None
        next_parent = parent
        if semantic_id is not None:
            if not isinstance(semantic_id, str) or not semantic_id:
                raise _DiffInputError("semantic IDs must be nonempty strings")
            if semantic_id in raw:
                raise _DiffInputError(f"duplicate semantic ID {semantic_id!r}")
            raw[semantic_id] = (value, parent)
            export_id = value.get("id")
            if not isinstance(export_id, (str, int)):
                raise _DiffInputError(f"identity {semantic_id!r} has no export ID")
            export_key = str(export_id)
            if export_key in export_ids:
                raise _DiffInputError(f"duplicate export ID {export_key!r}")
            export_ids[export_key] = semantic_id
            if "sourceId" not in value and "destinationId" not in value:
                next_parent = semantic_id
        for key, child in value.items():
            if key != "properties":
                visit(child, next_parent)

    visit(payload["model"])
    expected = artifact.contract.semantic_ids
    if set(raw) != set(expected):
        missing = sorted(set(expected) - set(raw))
        extra = sorted(set(raw) - set(expected))
        raise _DiffInputError(
            f"contract/render identity mismatch; missing={missing}, extra={extra}"
        )

    identities: dict[str, _Identity] = {}
    for semantic_id, (value, parent) in raw.items():
        relationship = "sourceId" in value or "destinationId" in value
        if relationship:
            source = _resolve_export_id(value.get("sourceId"), export_ids, semantic_id)
            destination = _resolve_export_id(
                value.get("destinationId"), export_ids, semantic_id
            )
            identities[semantic_id] = _Identity(
                kind="relationship",
                semantic_id=semantic_id,
                properties=_semantic_properties(
                    value, export_ids, relationship=True
                ),
                parent=None,
                source=source,
                destination=destination,
            )
        else:
            identities[semantic_id] = _Identity(
                kind="element",
                semantic_id=semantic_id,
                properties=_semantic_properties(
                    value, export_ids, relationship=False
                ),
                parent=parent,
            )

    views_payload = payload.get("views")
    if not isinstance(views_payload, dict):
        raise _DiffInputError("workspace JSON has no views object")
    views: dict[str, _View] = {}
    for collection, entries in views_payload.items():
        if not collection.endswith("Views"):
            continue
        if not isinstance(entries, list):
            raise _DiffInputError(f"view collection {collection!r} is invalid")
        for value in entries:
            if not isinstance(value, dict) or not isinstance(value.get("key"), str):
                raise _DiffInputError(f"view in {collection!r} has no key")
            key = value["key"]
            if key in views:
                raise _DiffInputError(f"duplicate view key {key!r}")
            views[key] = _View(
                key=key,
                properties=_view_properties(collection, value, export_ids),
                elements=_view_members(
                    value.get("elements", []), export_ids, identities, "element", key
                ),
                relationships=_view_members(
                    value.get("relationships", []),
                    export_ids,
                    identities,
                    "relationship",
                    key,
                ),
            )
    expected_views = {view.key for view in artifact.contract.views}
    if set(views) != expected_views or set(views) != set(artifact.render.view_keys):
        raise _DiffInputError("contract/render view inventories disagree")
    return _Model(identities, views)


def _resolve_export_id(value: object, export_ids: dict[str, str], owner: str) -> str:
    if not isinstance(value, (str, int)) or str(value) not in export_ids:
        raise _DiffInputError(f"identity {owner!r} has an unresolved endpoint")
    return export_ids[str(value)]


def _semantic_properties(
    value: dict[str, object],
    export_ids: dict[str, str],
    *,
    relationship: bool,
) -> object:
    excluded = {"id", "sourceId", "destinationId", "linkedRelationshipId"}
    if not relationship:
        excluded |= set(_MODEL_CHILD_KEYS)
    semantic = {key: item for key, item in value.items() if key not in excluded}
    for key in ("softwareSystemId", "containerId", "componentId", "parentId"):
        if key in semantic and isinstance(semantic[key], (str, int)):
            export_id = str(semantic[key])
            if export_id not in export_ids:
                raise _DiffInputError(f"identity has unresolved {key}")
            semantic[key] = export_ids[export_id]
    return _canonical(semantic)


def _canonical(value: object) -> object:
    if isinstance(value, dict):
        return tuple(
            (key, _canonical(item))
            for key, item in sorted(value.items())
            if key not in {_SEMANTIC_ID, _DSL_ID}
        )
    if isinstance(value, list):
        return tuple(sorted((_canonical(item) for item in value), key=repr))
    return value


def _view_properties(
    collection: str, value: dict[str, object], export_ids: dict[str, str]
) -> object:
    result: dict[str, object] = {"viewType": collection}
    for key, item in value.items():
        if key in _VIEW_MEMBER_KEYS or key in _VIEW_LAYOUT_KEYS or key == "key":
            continue
        if key in _VIEW_MODEL_SCOPE_IDS:
            if not isinstance(item, (str, int)) or str(item) not in export_ids:
                raise _DiffInputError(
                    f"view {value.get('key')!r} has unresolved {key}"
                )
            result[key] = export_ids[str(item)]
        elif key == "deploymentEnvironmentId":
            if not isinstance(item, str) or not item:
                raise _DiffInputError(
                    f"view {value.get('key')!r} has invalid deploymentEnvironmentId"
                )
            # Structurizr uses the deployment environment name here, not a model ID.
            result[key] = item
        elif key != "id":
            result[key] = item
    return _canonical(result)


def _view_members(
    raw: object,
    export_ids: dict[str, str],
    identities: dict[str, _Identity],
    expected_kind: Literal["element", "relationship"],
    view_key: str,
) -> frozenset[str]:
    if not isinstance(raw, list):
        raise _DiffInputError(f"view {view_key!r} membership is invalid")
    members: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), (str, int)):
            raise _DiffInputError(f"view {view_key!r} has invalid membership")
        semantic_id = export_ids.get(str(item["id"]))
        if semantic_id is None:
            raise _DiffInputError(f"view {view_key!r} has unresolved membership")
        if identities[semantic_id].kind != expected_kind:
            raise _DiffInputError(
                f"view {view_key!r} has {expected_kind} membership with the wrong kind"
            )
        members.add(semantic_id)
    return frozenset(members)


def _applicable_renames(
    current: _Model, proposed: _Model, contract: C4WorkspaceContract
) -> dict[str, str]:
    renames: dict[str, str] = {}
    for rename in contract.renames:
        old = current.identities.get(rename.old_semantic_id)
        new = proposed.identities.get(rename.new_semantic_id)
        if old is None:
            continue
        if new is None or old.kind != new.kind:
            raise _DiffInputError(
                f"reviewed rename {rename.old_semantic_id!r} has incompatible identity"
            )
        renames[rename.old_semantic_id] = rename.new_semantic_id
    return renames


def _compare_identities(
    current: _Model, proposed: _Model, renames: dict[str, str]
) -> tuple[tuple[C4IdentityChange, ...], tuple[C4ContainmentChange, ...]]:
    reverse = {new: old for old, new in renames.items()}
    current_matched = set(renames)
    changes: list[C4IdentityChange] = []
    containment: list[C4ContainmentChange] = []

    for proposed_id in sorted(proposed.identities):
        old_id = reverse.get(proposed_id, proposed_id)
        before = current.identities.get(old_id)
        after = proposed.identities[proposed_id]
        if before is None:
            changes.append(C4IdentityChange(after.kind, proposed_id, "added"))
            continue
        current_matched.add(old_id)
        fields: list[str] = []
        if before.kind != after.kind:
            raise _DiffInputError(f"identity {proposed_id!r} changed kind")
        if before.properties != after.properties:
            fields.append("properties")
        if after.kind == "relationship":
            before_source = renames.get(before.source or "", before.source)
            before_destination = renames.get(before.destination or "", before.destination)
            if (before_source, before_destination) != (after.source, after.destination):
                fields.append("endpoints")
        before_parent = renames.get(before.parent or "", before.parent)
        if after.kind == "element" and before_parent != after.parent:
            containment.append(
                C4ContainmentChange(proposed_id, before_parent, after.parent)
            )
        changes.append(
            C4IdentityChange(
                after.kind,
                proposed_id,
                "changed" if fields else "unchanged",
                old_id if old_id != proposed_id else None,
                tuple(fields),
            )
        )
    for current_id in sorted(set(current.identities) - current_matched):
        before = current.identities[current_id]
        changes.append(C4IdentityChange(before.kind, current_id, "removed"))
    changes.sort(key=lambda item: (item.kind, item.semantic_id))
    containment.sort(key=lambda item: item.semantic_id)
    return tuple(changes), tuple(containment)


def _compare_views(
    current: _Model,
    proposed: _Model,
    renames: dict[str, str],
    identities: tuple[C4IdentityChange, ...],
    containment: tuple[C4ContainmentChange, ...],
    initial_state: DiffState | None,
) -> tuple[C4ViewDiff, ...]:
    semantically_changed = {
        item.semantic_id for item in identities if item.state != "unchanged"
    } | {item.semantic_id for item in containment}
    views: list[C4ViewDiff] = []
    for key in sorted(set(current.views) | set(proposed.views)):
        before = current.views.get(key)
        after = proposed.views.get(key)
        current_elements = _renamed_members(before.elements if before else frozenset(), renames)
        current_relationships = _renamed_members(
            before.relationships if before else frozenset(), renames
        )
        proposed_elements = after.elements if after else frozenset()
        proposed_relationships = after.relationships if after else frozenset()
        members = (
            current_elements
            | current_relationships
            | proposed_elements
            | proposed_relationships
        )
        changed = tuple(sorted(members & semantically_changed))
        if initial_state:
            state: ViewState = initial_state  # type: ignore[assignment]
        elif before is None:
            state = "added"
        elif after is None:
            state = "removed_view"
        elif (
            before.properties != after.properties
            or current_elements != proposed_elements
            or current_relationships != proposed_relationships
            or changed
        ):
            state = "changed"
        else:
            state = "unchanged"
        views.append(
            C4ViewDiff(
                key=key,
                state=state,
                current_elements=tuple(sorted(current_elements)),
                proposed_elements=tuple(sorted(proposed_elements)),
                current_relationships=tuple(sorted(current_relationships)),
                proposed_relationships=tuple(sorted(proposed_relationships)),
                changed_identities=changed,
            )
        )
    return tuple(views)


def _renamed_members(values: frozenset[str], renames: dict[str, str]) -> frozenset[str]:
    return frozenset(renames.get(value, value) for value in values)
