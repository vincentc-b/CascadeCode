"""Trusted hit-target bindings for one Structurizr static export."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


BindingKind = Literal["element", "relationship"]
_SEMANTIC_PROPERTIES = ("cascade.semanticId", "cascade.id")
_DANGEROUS_ELEMENTS = {
    "script",
    "style",
    "foreignobject",
    "iframe",
    "object",
    "embed",
}
_APPROVED_BINDING_ATTRIBUTES = {
    "data-cascade-model-kind",
    "data-cascade-export-id",
}
_LOCAL_URL = re.compile(r"url\(\s*#[^)]+\s*\)\Z", re.IGNORECASE)


class C4BindingError(ValueError):
    """A rendered target cannot be joined to one trusted semantic identity."""


@dataclass(frozen=True)
class C4HitTargetBinding:
    view_key: str
    renderer_node_id: str
    kind: BindingKind
    export_id: str
    semantic_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "view_key": self.view_key,
            "renderer_node_id": self.renderer_node_id,
            "kind": self.kind,
            "export_id": self.export_id,
            "semantic_id": self.semantic_id,
        }


def verify_and_sanitize_hit_targets(
    *,
    workspace: dict[str, object],
    view_key: str,
    raw_bindings: Path,
    raw_svg: Path,
    sanitized_svg: Path,
    expected_semantic_ids: frozenset[str],
) -> tuple[C4HitTargetBinding, ...]:
    """Join live renderer metadata to this export and verify sanitized SVG output."""

    objects = _model_objects(workspace)
    rows = _binding_rows(raw_bindings)
    bindings: list[C4HitTargetBinding] = []
    renderer_nodes: set[str] = set()
    semantic_targets: set[str] = set()
    for index, row in enumerate(rows):
        renderer_node_id = _required_text(row.get("rendererNodeId"), index, "rendererNodeId")
        kind = row.get("kind")
        if kind not in ("element", "relationship"):
            raise C4BindingError(
                f"view {view_key!r} target {renderer_node_id!r} has no trusted model kind"
            )
        export_id = _required_text(row.get("modelId"), index, "modelId")
        if renderer_node_id in renderer_nodes:
            raise C4BindingError(
                f"view {view_key!r} has duplicate renderer target {renderer_node_id!r}"
            )
        semantic_id = _resolve_semantic_id(export_id, kind, objects)
        if semantic_id not in expected_semantic_ids:
            raise C4BindingError(
                f"view {view_key!r} target {renderer_node_id!r} resolves to stale semantic ID "
                f"{semantic_id!r}"
            )
        if semantic_id in semantic_targets:
            raise C4BindingError(
                f"view {view_key!r} has ambiguous duplicate semantic target {semantic_id!r}"
            )
        renderer_nodes.add(renderer_node_id)
        semantic_targets.add(semantic_id)
        bindings.append(
            C4HitTargetBinding(
                view_key=view_key,
                renderer_node_id=renderer_node_id,
                kind=kind,
                export_id=export_id,
                semantic_id=semantic_id,
            )
        )

    expected_svg = {
        binding.renderer_node_id: (binding.kind, binding.export_id)
        for binding in bindings
    }
    tree = ET.parse(raw_svg)
    _sanitize_svg(tree)
    if _svg_bindings(tree, view_key) != expected_svg:
        raise C4BindingError(
            f"view {view_key!r} serialized SVG attributes do not match captured targets"
        )
    sanitized_svg.parent.mkdir(parents=True, exist_ok=True)
    tree.write(sanitized_svg, encoding="utf-8", xml_declaration=True)
    persisted = ET.parse(sanitized_svg)
    if _svg_bindings(persisted, view_key) != expected_svg:
        raise C4BindingError(
            f"view {view_key!r} binding attributes did not survive SVG sanitization"
        )
    return tuple(bindings)


def validate_hit_target_manifest(
    *,
    workspace: dict[str, object],
    manifest: object,
    artifact_root: Path,
    expected_view_keys: tuple[str, ...],
    expected_semantic_ids: frozenset[str],
) -> tuple[Path, ...]:
    """Validate a persisted manifest and prove its SVGs still match exactly."""

    if not isinstance(manifest, dict) or set(manifest) != {
        "version",
        "interactive",
        "source_diff_reference",
        "views",
    }:
        raise C4BindingError("hit-target manifest has an invalid shape")
    if manifest["version"] != 1 or manifest["interactive"] is not True:
        raise C4BindingError("hit-target manifest is not interactive")
    if not isinstance(manifest["source_diff_reference"], str) or not manifest[
        "source_diff_reference"
    ]:
        raise C4BindingError("hit-target manifest has no source diff reference")
    views = manifest["views"]
    if not isinstance(views, list):
        raise C4BindingError("hit-target manifest views must be a list")
    if [row.get("view_key") if isinstance(row, dict) else None for row in views] != list(
        expected_view_keys
    ):
        raise C4BindingError("hit-target manifest view inventory is stale")

    objects = _model_objects(workspace)
    svg_paths: list[Path] = []
    for row in views:
        if not isinstance(row, dict) or set(row) != {"view_key", "svg", "targets"}:
            raise C4BindingError("hit-target manifest view has an invalid shape")
        view_key = row["view_key"]
        svg_path = _confined_artifact_path(artifact_root, row["svg"])
        targets = row["targets"]
        if not isinstance(targets, list):
            raise C4BindingError(f"view {view_key!r} targets must be a list")
        expected: dict[str, tuple[str, str]] = {}
        semantics: set[str] = set()
        for target in targets:
            if not isinstance(target, dict) or set(target) != {
                "view_key",
                "renderer_node_id",
                "kind",
                "export_id",
                "semantic_id",
            }:
                raise C4BindingError(f"view {view_key!r} target has an invalid shape")
            if target["view_key"] != view_key:
                raise C4BindingError(f"view {view_key!r} target names another view")
            renderer_id = target["renderer_node_id"]
            kind = target["kind"]
            export_id = target["export_id"]
            semantic_id = target["semantic_id"]
            if (
                not isinstance(renderer_id, str)
                or not renderer_id
                or kind not in ("element", "relationship")
                or not isinstance(export_id, str)
                or not export_id
                or not isinstance(semantic_id, str)
                or not semantic_id
                or renderer_id in expected
                or semantic_id in semantics
            ):
                raise C4BindingError(f"view {view_key!r} has an ambiguous target")
            if semantic_id not in expected_semantic_ids or _resolve_semantic_id(
                export_id, kind, objects
            ) != semantic_id:
                raise C4BindingError(f"view {view_key!r} target identity is stale")
            expected[renderer_id] = (kind, export_id)
            semantics.add(semantic_id)
        tree = ET.parse(svg_path)
        before = ET.tostring(tree.getroot(), encoding="utf-8")
        _sanitize_svg(tree)
        if ET.tostring(tree.getroot(), encoding="utf-8") != before:
            raise C4BindingError(f"view {view_key!r} SVG is not sanitized")
        if _svg_bindings(tree, view_key) != expected:
            raise C4BindingError(f"view {view_key!r} SVG bindings are stale")
        svg_paths.append(svg_path)
    return tuple(svg_paths)


def _confined_artifact_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise C4BindingError("hit-target manifest SVG path is invalid")
    relative = Path(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise C4BindingError("hit-target manifest SVG path escapes the artifact")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise C4BindingError("hit-target manifest SVG path escapes the artifact") from exc
    if not path.is_file():
        raise C4BindingError("hit-target manifest names a missing SVG")
    return path


def _binding_rows(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise C4BindingError("renderer binding capture is not valid JSON") from exc
    if not isinstance(payload, list):
        raise C4BindingError("renderer binding capture must be a list")
    rows: list[dict[str, object]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or set(row) != {"rendererNodeId", "kind", "modelId"}:
            raise C4BindingError(f"renderer binding {index} has an invalid shape")
        rows.append(row)
    return rows


def _required_text(value: object, index: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise C4BindingError(f"renderer binding {index} has no {field}")
    return value


def _model_objects(workspace: dict[str, object]) -> dict[str, dict[str, object]]:
    model = workspace.get("model")
    if not isinstance(model, dict):
        raise C4BindingError("embedded workspace has no model object")
    objects: dict[str, dict[str, object]] = {}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            identifier = value.get("id")
            if isinstance(identifier, str):
                if not identifier or identifier in objects:
                    raise C4BindingError(
                        f"embedded workspace has ambiguous export ID {identifier!r}"
                    )
                objects[identifier] = value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(model)
    return objects


def _resolve_semantic_id(
    export_id: str,
    kind: BindingKind,
    objects: dict[str, dict[str, object]],
) -> str:
    current_id = export_id
    seen: set[str] = set()
    while current_id not in seen:
        seen.add(current_id)
        current = objects.get(current_id)
        if current is None:
            raise C4BindingError(f"export ID {current_id!r} is absent from embedded workspace")
        actual_kind: BindingKind = (
            "relationship"
            if "sourceId" in current
            or "destinationId" in current
            or "linkedRelationshipId" in current
            else "element"
        )
        if actual_kind != kind:
            raise C4BindingError(
                f"export ID {current_id!r} is {actual_kind}, not captured kind {kind}"
            )
        semantic_id = _semantic_property(current, current_id)
        if semantic_id is not None:
            return semantic_id
        next_id = (
            current.get("linkedRelationshipId")
            if kind == "relationship"
            else current.get("containerId")
        )
        if not isinstance(next_id, str) or not next_id:
            raise C4BindingError(f"export ID {current_id!r} has no semantic identity chain")
        current_id = next_id
    raise C4BindingError(f"export ID {export_id!r} has a cyclic semantic identity chain")


def _semantic_property(item: dict[str, object], export_id: str) -> str | None:
    properties = item.get("properties", {})
    if not isinstance(properties, dict):
        raise C4BindingError(f"export ID {export_id!r} has invalid properties")
    values = [properties.get(name) for name in _SEMANTIC_PROPERTIES if name in properties]
    if not values:
        return None
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise C4BindingError(f"export ID {export_id!r} has an empty semantic ID")
    if len(set(values)) != 1:
        raise C4BindingError(f"export ID {export_id!r} has conflicting semantic IDs")
    return values[0]


def _sanitize_svg(tree: ET.ElementTree) -> None:
    root = tree.getroot()
    if _local_name(root.tag) != "svg":
        raise C4BindingError("bound renderer output is not SVG")

    def clean(parent: ET.Element) -> None:
        for child in list(parent):
            if _local_name(child.tag).lower() in _DANGEROUS_ELEMENTS:
                parent.remove(child)
            else:
                clean(child)

    clean(root)
    for node in root.iter():
        for attribute, value in list(node.attrib.items()):
            local = _local_name(attribute)
            lowered = local.lower()
            if lowered.startswith("on"):
                del node.attrib[attribute]
            elif lowered.startswith("data-cascade-") and local not in _APPROVED_BINDING_ATTRIBUTES:
                del node.attrib[attribute]
            elif lowered == "href" and not value.startswith("#"):
                del node.attrib[attribute]
            elif "url(" in value.lower() and _LOCAL_URL.fullmatch(value.strip()) is None:
                del node.attrib[attribute]


def _svg_bindings(
    tree: ET.ElementTree, view_key: str
) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for node in tree.getroot().iter():
        kind = node.attrib.get("data-cascade-model-kind")
        export_id = node.attrib.get("data-cascade-export-id")
        if kind is None and export_id is None:
            continue
        identifier = node.attrib.get("id")
        if (
            not identifier
            or kind not in ("element", "relationship")
            or not export_id
            or identifier in result
        ):
            raise C4BindingError(f"view {view_key!r} contains an invalid bound SVG target")
        result[identifier] = (kind, export_id)
    return result


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]
