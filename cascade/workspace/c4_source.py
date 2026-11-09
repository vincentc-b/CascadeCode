"""Validation for repository-owned Structurizr DSL source.

The renderer is deliberately not involved here.  This module validates the
small source contract that Cascade owns before any untrusted or export-local
identifier can enter the rendering pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cascade.workspace.errors import WorkspaceError

_SEMANTIC_ID = re.compile(r"[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*\Z")
_DSL_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ELEMENT = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(person|softwareSystem|container|component|deploymentNode|"
    r"infrastructureNode|softwareSystemInstance|containerInstance|element)\b"
)
_RELATIONSHIP = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*->\s*([A-Za-z_][A-Za-z0-9_]*)\b"
)
_UNASSIGNED_RELATIONSHIP = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*->\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\b"
)
_VIEW = re.compile(
    r'^\s*(systemLandscape|systemContext|container|component|dynamic|deployment)'
    r'(?:\s+[A-Za-z_][A-Za-z0-9_]*)?\s+"([^"]*)"\s*\{'
)
_VIEW_DIRECTIVE = re.compile(
    r"^\s*(systemLandscape|systemContext|container|component|dynamic|deployment|"
    r"filtered|custom|image)\b"
)
_INCLUDE = re.compile(r"^\s*!include\s+(.+?)\s*$")
_SEMANTIC_PROPERTY = re.compile(r'"cascade\.semanticId"\s+"([^"]*)"')
_FORBIDDEN_DIRECTIVE = re.compile(
    r"^\s*!(plugin|script|components|extend)\b", re.IGNORECASE
)
_REMOTE_REFERENCE = re.compile(r"(?:https?|ftp)://", re.IGNORECASE)
_REMOTE_SOURCE = re.compile(
    r"^\s*(?:!include|theme|icon|logo|plantuml|mermaid|kroki|image)\b.*"
    r"(?:https?|ftp)://",
    re.IGNORECASE,
)
_WORKSPACE_EXTENSION = re.compile(r"^\s*workspace\s+extends\b", re.IGNORECASE)


class C4SourceError(WorkspaceError):
    """The versioned C4 source is unsafe or semantically ambiguous."""


@dataclass(frozen=True)
class C4Element:
    dsl_identifier: str
    semantic_id: str
    fragment: Path


@dataclass(frozen=True)
class C4Relationship:
    dsl_identifier: str
    semantic_id: str
    source: str
    destination: str
    fragment: Path


@dataclass(frozen=True)
class C4View:
    key: str
    fragment: Path


@dataclass(frozen=True)
class C4Rename:
    old_semantic_id: str
    new_semantic_id: str
    reviewed_by: str


@dataclass(frozen=True)
class C4WorkspaceContract:
    root: Path
    source: Path
    owner: str
    fragment_owners: dict[Path, str]
    elements: tuple[C4Element, ...]
    relationships: tuple[C4Relationship, ...]
    views: tuple[C4View, ...]
    renames: tuple[C4Rename, ...]

    @property
    def semantic_ids(self) -> frozenset[str]:
        return frozenset(
            item.semantic_id for item in (*self.elements, *self.relationships)
        )


@dataclass(frozen=True)
class _Declaration:
    kind: str
    dsl_identifier: str
    semantic_id: str
    fragment: Path
    source: str | None = None
    destination: str | None = None


def validate_c4_workspace(root: Path | str) -> C4WorkspaceContract:
    """Validate a workspace contract and its complete local DSL include closure."""

    root_path = Path(root).resolve()
    manifest_path = root_path / "workspace.contract.json"
    payload = _read_json_object(manifest_path)
    _require_exact_fields(
        payload,
        {"version", "workspace", "fragments", "elements", "relationships", "views", "renames"},
        "workspace contract",
    )
    if payload["version"] != 1:
        raise C4SourceError("unsupported C4 workspace contract version")

    workspace = _object(payload["workspace"], "workspace")
    _require_exact_fields(workspace, {"source", "owner"}, "workspace")
    owner = _nonblank(workspace["owner"], "workspace.owner")
    source = _safe_relative(root_path, workspace["source"], "workspace.source")

    fragment_owners: dict[Path, str] = {}
    for index, raw in enumerate(_list(payload["fragments"], "fragments")):
        row = _object(raw, f"fragments[{index}]")
        _require_exact_fields(row, {"path", "owner"}, f"fragments[{index}]")
        path = _safe_relative(root_path, row["path"], f"fragments[{index}].path")
        if path in fragment_owners or path == source:
            raise C4SourceError(f"duplicate C4 fragment path: {path.as_posix()}")
        fragment_owners[path] = _nonblank(row["owner"], f"fragments[{index}].owner")

    closure = _load_source_closure(root_path, source)
    _validate_implied_relationship_setting(closure, source)
    declared_fragments = set(fragment_owners)
    actual_fragments = set(closure) - {source}
    if declared_fragments != actual_fragments:
        missing = sorted(path.as_posix() for path in actual_fragments - declared_fragments)
        extra = sorted(path.as_posix() for path in declared_fragments - actual_fragments)
        raise C4SourceError(
            f"C4 fragment ownership does not match include closure; missing={missing}, extra={extra}"
        )

    declarations, source_views = _scan_sources(closure)
    elements = _parse_elements(payload["elements"], root_path)
    relationships = _parse_relationships(payload["relationships"], root_path)
    views = _parse_views(payload["views"], root_path)
    renames = _parse_renames(payload["renames"])

    _validate_declarations(declarations, elements, relationships)
    _validate_views(source_views, views)
    _validate_semantic_ids(elements, relationships)
    _validate_references(elements, relationships)
    _validate_membership(source, fragment_owners, elements, relationships, views)
    _validate_renames(renames, elements, relationships)

    return C4WorkspaceContract(
        root=root_path,
        source=source,
        owner=owner,
        fragment_owners=fragment_owners,
        elements=elements,
        relationships=relationships,
        views=views,
        renames=renames,
    )


def _load_source_closure(root: Path, source: Path) -> dict[Path, str]:
    loaded: dict[Path, str] = {}

    def visit(relative: Path) -> None:
        if relative in loaded:
            return
        absolute = root / relative
        try:
            resolved = absolute.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise C4SourceError(f"C4 source escapes its architecture root: {relative}") from exc
        if not resolved.is_file() or resolved.suffix != ".dsl":
            raise C4SourceError(f"C4 source must be a local .dsl file: {relative}")
        text = resolved.read_text(encoding="utf-8")
        loaded[relative] = text
        for line_number, line in enumerate(text.splitlines(), 1):
            if _REMOTE_SOURCE.match(line):
                raise C4SourceError(f"remote C4 references are forbidden: {relative}")
            if _WORKSPACE_EXTENSION.match(line):
                raise C4SourceError(
                    f"workspace extension is forbidden at {relative}:{line_number}"
                )
            if _FORBIDDEN_DIRECTIVE.match(line):
                raise C4SourceError(
                    f"executable or inherited DSL extension is forbidden at {relative}:{line_number}"
                )
            include = _INCLUDE.match(line)
            if include:
                raw = include.group(1).strip().strip('"')
                if _REMOTE_REFERENCE.search(raw):
                    raise C4SourceError(f"remote C4 references are forbidden: {relative}")
                candidate = _safe_relative(root, relative.parent / raw, "!include")
                visit(candidate)

    visit(source)
    return loaded


def _scan_sources(
    closure: dict[Path, str],
) -> tuple[dict[tuple[str, str], _Declaration], dict[str, Path]]:
    declarations: dict[tuple[str, str], _Declaration] = {}
    dsl_ids: dict[str, tuple[str, Path]] = {}
    views: dict[str, Path] = {}
    for fragment, text in closure.items():
        lines = text.splitlines()
        for line_number, line in enumerate(lines, 1):
            relationship = _RELATIONSHIP.match(line)
            element = _ELEMENT.match(line) if relationship is None else None
            if relationship or element:
                match = relationship or element
                assert match is not None
                dsl_id = match.group(1)
                prior = dsl_ids.get(dsl_id)
                if prior is not None:
                    raise C4SourceError(
                        f"duplicate DSL identifier {dsl_id!r} at {fragment}:{line_number}; "
                        f"first declared in {prior[1]}"
                    )
                semantic_id = _semantic_property(lines, line_number - 1, fragment)
                kind = "relationship" if relationship else "element"
                declaration = _Declaration(
                    kind=kind,
                    dsl_identifier=dsl_id,
                    semantic_id=semantic_id,
                    fragment=fragment,
                    source=relationship.group(2) if relationship else None,
                    destination=relationship.group(3) if relationship else None,
                )
                declarations[(kind, dsl_id)] = declaration
                dsl_ids[dsl_id] = (kind, fragment)
                continue
            unsupported = _UNASSIGNED_RELATIONSHIP.match(line)
            if unsupported:
                raise C4SourceError(
                    "dynamic occurrences and unassigned/derived relationships are unsupported "
                    f"until they have deterministic source/view/occurrence identity ({fragment}:{line_number})"
                )
            view = _VIEW.match(line)
            if view:
                if view.group(1) == "dynamic":
                    raise C4SourceError(
                        "dynamic views are unsupported until each occurrence has deterministic "
                        f"source/view/occurrence identity ({fragment}:{line_number})"
                    )
                key = view.group(2)
                if not key:
                    raise C4SourceError(f"view key is missing at {fragment}:{line_number}")
                if key in views:
                    raise C4SourceError(f"duplicate view key {key!r}")
                views[key] = fragment
            elif _VIEW_DIRECTIVE.match(line):
                raise C4SourceError(
                    f"view must use supported syntax with an explicit key ({fragment}:{line_number})"
                )
    return declarations, views


def _validate_implied_relationship_setting(
    closure: dict[Path, str], source: Path
) -> None:
    settings: list[tuple[Path, int, str]] = []
    for fragment, text in closure.items():
        for line_number, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("!impliedRelationships"):
                settings.append((fragment, line_number, line.strip()))
    if (
        len(settings) != 1
        or settings[0][0] != source
        or settings[0][2] != "!impliedRelationships false"
    ):
        raise C4SourceError(
            "workspace must set !impliedRelationships false exactly once; derived "
            "relationships are unsupported without deterministic source identity"
        )


def _semantic_property(lines: list[str], start: int, fragment: Path) -> str:
    if "{" not in lines[start]:
        raise C4SourceError(
            f"reviewable declaration must open a property block at {fragment}:{start + 1}"
        )
    depth = 0
    matches: list[str] = []
    for line in lines[start:]:
        depth += line.count("{") - line.count("}")
        # A declaration's own properties live one block below it. Nested C4
        # elements have deeper blocks and must not leak their IDs to a parent.
        if depth == 2:
            matches.extend(_SEMANTIC_PROPERTY.findall(line))
        if depth == 0:
            break
    if len(matches) != 1:
        raise C4SourceError(
            f"reviewable declaration at {fragment}:{start + 1} must contain exactly one "
            "cascade.semanticId property"
        )
    return matches[0]


def _parse_elements(raw: object, root: Path) -> tuple[C4Element, ...]:
    rows: list[C4Element] = []
    for index, item in enumerate(_list(raw, "elements")):
        row = _object(item, f"elements[{index}]")
        _require_exact_fields(row, {"dsl_identifier", "semantic_id", "fragment"}, f"elements[{index}]")
        rows.append(
            C4Element(
                dsl_identifier=_dsl_id(row["dsl_identifier"], f"elements[{index}].dsl_identifier"),
                semantic_id=_semantic_id(row["semantic_id"], f"elements[{index}].semantic_id"),
                fragment=_safe_relative(root, row["fragment"], f"elements[{index}].fragment"),
            )
        )
    return tuple(rows)


def _parse_relationships(raw: object, root: Path) -> tuple[C4Relationship, ...]:
    rows: list[C4Relationship] = []
    for index, item in enumerate(_list(raw, "relationships")):
        field = f"relationships[{index}]"
        row = _object(item, field)
        _require_exact_fields(
            row,
            {"dsl_identifier", "semantic_id", "source", "destination", "fragment"},
            field,
        )
        rows.append(
            C4Relationship(
                dsl_identifier=_dsl_id(row["dsl_identifier"], f"{field}.dsl_identifier"),
                semantic_id=_semantic_id(row["semantic_id"], f"{field}.semantic_id"),
                source=_dsl_id(row["source"], f"{field}.source"),
                destination=_dsl_id(row["destination"], f"{field}.destination"),
                fragment=_safe_relative(root, row["fragment"], f"{field}.fragment"),
            )
        )
    return tuple(rows)


def _parse_views(raw: object, root: Path) -> tuple[C4View, ...]:
    rows: list[C4View] = []
    for index, item in enumerate(_list(raw, "views")):
        field = f"views[{index}]"
        row = _object(item, field)
        _require_exact_fields(row, {"key", "fragment"}, field)
        rows.append(
            C4View(
                key=_nonblank(row["key"], f"{field}.key"),
                fragment=_safe_relative(root, row["fragment"], f"{field}.fragment"),
            )
        )
    return tuple(rows)


def _parse_renames(raw: object) -> tuple[C4Rename, ...]:
    rows: list[C4Rename] = []
    for index, item in enumerate(_list(raw, "renames")):
        field = f"renames[{index}]"
        row = _object(item, field)
        _require_exact_fields(row, {"old_semantic_id", "new_semantic_id", "reviewed_by"}, field)
        rows.append(
            C4Rename(
                old_semantic_id=_semantic_id(row["old_semantic_id"], f"{field}.old_semantic_id"),
                new_semantic_id=_semantic_id(row["new_semantic_id"], f"{field}.new_semantic_id"),
                reviewed_by=_nonblank(row["reviewed_by"], f"{field}.reviewed_by"),
            )
        )
    return tuple(rows)


def _validate_declarations(
    declarations: dict[tuple[str, str], _Declaration],
    elements: tuple[C4Element, ...],
    relationships: tuple[C4Relationship, ...],
) -> None:
    expected: dict[tuple[str, str], tuple[str, Path, str | None, str | None]] = {}
    for item in elements:
        key = ("element", item.dsl_identifier)
        if key in expected:
            raise C4SourceError(f"duplicate contract DSL identifier {item.dsl_identifier!r}")
        expected[key] = (item.semantic_id, item.fragment, None, None)
    for item in relationships:
        key = ("relationship", item.dsl_identifier)
        if key in expected:
            raise C4SourceError(f"duplicate contract DSL identifier {item.dsl_identifier!r}")
        expected[key] = (
            item.semantic_id,
            item.fragment,
            item.source,
            item.destination,
        )
    if set(expected) != set(declarations):
        missing = sorted(set(declarations) - set(expected))
        extra = sorted(set(expected) - set(declarations))
        raise C4SourceError(f"contract does not cover DSL declarations; missing={missing}, extra={extra}")
    for key, (semantic_id, fragment, source, destination) in expected.items():
        actual = declarations[key]
        if (
            actual.semantic_id != semantic_id
            or actual.fragment != fragment
            or actual.source != source
            or actual.destination != destination
        ):
            raise C4SourceError(f"contract disagrees with DSL declaration {key[1]!r}")


def _validate_views(source_views: dict[str, Path], views: tuple[C4View, ...]) -> None:
    contract: dict[str, Path] = {}
    for view in views:
        if view.key in contract:
            raise C4SourceError(f"duplicate contract view key {view.key!r}")
        contract[view.key] = view.fragment
    if contract != source_views:
        raise C4SourceError("contract view keys do not exactly match explicit DSL view keys")


def _validate_semantic_ids(
    elements: tuple[C4Element, ...], relationships: tuple[C4Relationship, ...]
) -> None:
    seen: dict[str, str] = {}
    for item in (*elements, *relationships):
        prior = seen.get(item.semantic_id)
        if prior is not None:
            raise C4SourceError(
                f"duplicate workspace semantic ID {item.semantic_id!r}: {prior!r} and {item.dsl_identifier!r}"
            )
        seen[item.semantic_id] = item.dsl_identifier


def _validate_references(
    elements: tuple[C4Element, ...], relationships: tuple[C4Relationship, ...]
) -> None:
    identifiers = {item.dsl_identifier for item in elements}
    for relationship in relationships:
        if relationship.source not in identifiers or relationship.destination not in identifiers:
            raise C4SourceError(
                f"relationship {relationship.dsl_identifier!r} references an unknown element"
            )


def _validate_membership(
    source: Path,
    fragment_owners: dict[Path, str],
    elements: tuple[C4Element, ...],
    relationships: tuple[C4Relationship, ...],
    views: tuple[C4View, ...],
) -> None:
    allowed = set(fragment_owners) | {source}
    for item in (*elements, *relationships, *views):
        if item.fragment not in allowed:
            raise C4SourceError(f"contract item belongs to an unowned fragment: {item.fragment}")


def _validate_renames(
    renames: tuple[C4Rename, ...],
    elements: tuple[C4Element, ...],
    relationships: tuple[C4Relationship, ...],
) -> None:
    current = {item.semantic_id for item in (*elements, *relationships)}
    old_ids: set[str] = set()
    new_ids: set[str] = set()
    for rename in renames:
        if rename.old_semantic_id == rename.new_semantic_id:
            raise C4SourceError("rename mapping must change the semantic ID")
        if rename.old_semantic_id in current:
            raise C4SourceError("rename mapping old semantic ID is still active")
        if rename.new_semantic_id not in current:
            raise C4SourceError("rename mapping new semantic ID is not active")
        if rename.old_semantic_id in old_ids or rename.new_semantic_id in new_ids:
            raise C4SourceError("rename mapping is ambiguous")
        old_ids.add(rename.old_semantic_id)
        new_ids.add(rename.new_semantic_id)


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise C4SourceError(f"invalid C4 workspace contract: {path}") from exc
    return _object(payload, "workspace contract")


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise C4SourceError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise C4SourceError(f"{field} must be a list")
    return value


def _require_exact_fields(value: dict[str, object], fields: set[str], field: str) -> None:
    if set(value) != fields:
        raise C4SourceError(f"{field} must contain exactly {sorted(fields)}")


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise C4SourceError(f"{field} must be a nonempty string")
    return value.strip()


def _dsl_id(value: object, field: str) -> str:
    text = _nonblank(value, field)
    if _DSL_ID.fullmatch(text) is None:
        raise C4SourceError(f"{field} is not a valid DSL identifier")
    return text


def _semantic_id(value: object, field: str) -> str:
    text = _nonblank(value, field)
    if _SEMANTIC_ID.fullmatch(text) is None:
        raise C4SourceError(f"{field} is not a valid semantic ID")
    return text


def _safe_relative(root: Path, value: object, field: str) -> Path:
    if isinstance(value, Path):
        candidate = value
    elif isinstance(value, str) and value:
        candidate = Path(value)
    else:
        raise C4SourceError(f"{field} must be a repository-relative path")
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise C4SourceError(f"{field} must be a confined repository-relative path")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise C4SourceError(f"{field} escapes the architecture root") from exc
    return resolved.relative_to(root)
