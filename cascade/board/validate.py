"""Heading-name and graph validation. Prose is not judged."""

from __future__ import annotations

import re
from pathlib import Path

from cascade.agent.providers import parse_provider_id
from cascade.board.errors import CycleError, SchemaError, StatusMismatch
from cascade.board.paths import infer_repo_root, legal_folder
from cascade.board.work_ids import validate_work_id_identity
from cascade.board.types import BoardIndex, WorkDoc, WorkMeta, WorkTier

_REQUIRED_HEADINGS: dict[WorkTier, tuple[str, ...]] = {
    "epic": (
        "Intent",
        "Macro-architecture",
        "Cross-module constraints",
        "Core dependencies",
        "Feature breakdown",
        "Open questions",
        "Decision log",
        "Amendment log",
    ),
    "feature": (
        "Parent Epic",
        "Scope",
        "Data structures",
        "API contracts",
        "Logic flow",
        "Task breakdown",
        "Risks & upward questions",
        "Decision log",
    ),
    "task": (
        "Parent Feature",
        "Depends on",
        "Acceptance criteria",
        "Files likely touched",
        "Implementation notes",
        "Skills",
        "Test plan",
        "Out of scope",
    ),
}
_TIER_DIR = {"epic": "epics", "feature": "features", "task": "tasks"}
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_EPIC_STACK_MODEL_KEYS = frozenset(
    {
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    }
)
_LEGAL_MODEL_KEYS: dict[WorkTier, frozenset[str]] = {
    "epic": _EPIC_STACK_MODEL_KEYS,
    "feature": frozenset({"feature_lead", "feature_architect"}),
    "task": frozenset({"swe"}),
}


def validate_doc(doc: WorkDoc, board: BoardIndex) -> None:
    """Raise SchemaError, StatusMismatch, or CycleError. Return None when the doc is valid."""

    meta = doc.meta
    _check_identity(meta)
    _check_model_frontmatter(meta)
    _check_reasoning_frontmatter(meta)
    _check_provider_frontmatter(meta)
    _check_approval_frontmatter(meta)
    if meta.tier in ("feature", "task") and not meta.parent:
        raise SchemaError(f"{meta.id} requires a parent")
    _check_folder(meta)
    _check_headings(doc)
    _check_skills(meta)

    nodes = dict(board.by_id)
    nodes[meta.id] = meta
    for dep_id in meta.depends_on:
        if dep_id not in nodes:
            raise SchemaError(f"{meta.id} depends_on {dep_id} which is not on the board")
    if meta.parent and meta.parent not in nodes:
        raise SchemaError(f"{meta.id} parent {meta.parent} is not on the board")
    _assert_acyclic(nodes)


def _check_identity(meta: WorkMeta) -> None:
    validate_work_id_identity(meta.id, tier=meta.tier, parent=meta.parent)
    stem = meta.path.stem
    if not (stem == meta.id or stem.startswith(meta.id + "_")):
        raise SchemaError(f"filename {meta.path.name} does not match id {meta.id}")
    if meta.parent_rev is not None and _SHA_RE.fullmatch(meta.parent_rev) is None:
        raise SchemaError("parent_rev must be a 40-character hex SHA or null")


def _check_approval_frontmatter(meta: WorkMeta) -> None:
    if meta.approved_at is not None and meta.tier != "feature":
        raise SchemaError(f"{meta.id} approved_at is only valid for features")
    if meta.plan_approved_at is not None and meta.tier != "epic":
        raise SchemaError(f"{meta.id} plan_approved_at is only valid for epics")


def _check_provider_frontmatter(meta: WorkMeta) -> None:
    if meta.provider is None:
        return
    if not isinstance(meta.provider, str) or not meta.provider.strip():
        raise SchemaError("provider must be a non-blank string")
    parse_provider_id(meta.provider)


def _check_model_frontmatter(meta: WorkMeta) -> None:
    if meta.model is not None and (not isinstance(meta.model, str) or not meta.model.strip()):
        raise SchemaError("model must be a non-blank string")
    if meta.models is None:
        return
    if not isinstance(meta.models, dict):
        raise SchemaError("models must be a mapping")
    legal = _LEGAL_MODEL_KEYS[meta.tier]
    for key, value in meta.models.items():
        if not isinstance(key, str):
            raise SchemaError("models must be a mapping with string keys")
        if key not in legal:
            raise SchemaError(f"{meta.id} models key {key!r} is not legal for tier {meta.tier}")
        if not isinstance(value, str) or not value.strip():
            raise SchemaError(f"models.{key} must be a non-blank string")


def _check_reasoning_frontmatter(meta: WorkMeta) -> None:
    if meta.reasoning is None:
        return
    if not isinstance(meta.reasoning, dict):
        raise SchemaError("reasoning must be a mapping")
    legal = _LEGAL_MODEL_KEYS[meta.tier]
    for key, value in meta.reasoning.items():
        if not isinstance(key, str):
            raise SchemaError("reasoning must be a mapping with string keys")
        if key not in legal:
            raise SchemaError(f"{meta.id} reasoning key {key!r} is not legal for tier {meta.tier}")
        if not isinstance(value, str) or not value.strip():
            raise SchemaError(f"reasoning.{key} must be a non-blank string")


def _check_folder(meta: WorkMeta) -> None:
    folder = meta.path.parent.name
    expected = legal_folder(meta.status)
    if folder != expected:
        raise StatusMismatch(
            f"{meta.id} status {meta.status} is not legal in {folder} (expected {expected})"
        )
    tier_dir = meta.path.parent.parent.name
    if tier_dir != _TIER_DIR[meta.tier]:
        raise SchemaError(f"{meta.id} tier {meta.tier} is not in docs/{_TIER_DIR[meta.tier]}/")


def _check_headings(doc: WorkDoc) -> None:
    found: set[str] = set()
    for line in doc.body.splitlines():
        if line.startswith("## "):
            found.add(line[3:].strip())
    missing = [name for name in _REQUIRED_HEADINGS[doc.meta.tier] if name not in found]
    if missing:
        raise SchemaError(f"{doc.meta.id} missing heading(s): {', '.join(missing)}")


def _check_skills(meta: WorkMeta) -> None:
    if not meta.skills:
        return
    root = infer_repo_root(meta.path)
    if root is None:
        raise SchemaError(f"{meta.id} skills require a path under docs/{{epics,features,tasks}}")
    root_resolved = root.resolve()
    for skill in meta.skills:
        path = Path(skill)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise SchemaError(f"{meta.id} skill path is not inside the repo: {path}")
        if not path.parts or any(part in {"", "."} for part in path.parts):
            raise SchemaError(f"{meta.id} skill path is not inside the repo: {path}")
        resolved = (root_resolved / path).resolve()
        if not resolved.is_relative_to(root_resolved):
            raise SchemaError(f"{meta.id} skill path is not inside the repo: {path}")


def _assert_acyclic(nodes: dict[str, WorkMeta]) -> None:
    edges: dict[str, list[str]] = {}
    for work_id, meta in nodes.items():
        linked = list(meta.depends_on)
        if meta.parent:
            linked.append(meta.parent)
        edges[work_id] = linked

    white, gray, black = 0, 1, 2
    color = {work_id: white for work_id in edges}

    def visit(node: str, stack: list[str]) -> None:
        if node not in edges:
            return
        state = color[node]
        if state == gray:
            start = stack.index(node)
            cycle = stack[start:] + [node]
            raise CycleError("cycle in depends_on/parent: " + " -> ".join(cycle))
        if state == black:
            return
        color[node] = gray
        stack.append(node)
        for nxt in edges[node]:
            visit(nxt, stack)
        stack.pop()
        color[node] = black

    for work_id in edges:
        if color[work_id] == white:
            visit(work_id, [])
