"""Scratch cwd materialization for epic, feature, and boss planning turns."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.store import list_board, read_doc
from cascade.epic.guard import tool_guard as epic_tool_guard
from cascade.feature.guard import tool_guard as feature_tool_guard

PlanningTier = Literal["epic", "feature", "boss"]


@dataclass(frozen=True)
class PlanningSandbox:
    """Ephemeral scratch tree plus the real repo root tools mutate."""

    scratch_dir: Path
    repo_root: Path
    tier: PlanningTier
    scope_id: str | None


def collect_epic_readable_paths(epic_id: str, *, root: Path) -> list[Path]:
    repo = Path(root).resolve()
    epic = read_doc(epic_id, root=repo)
    paths: list[Path] = [epic.meta.path.resolve()]

    board = list_board(repo)
    for meta in board.by_id.values():
        if meta.tier != "feature" or meta.parent != epic_id:
            continue
        if epic_tool_guard(meta.path, "read", epic_id=epic_id, root=repo):
            paths.append(meta.path.resolve())

    amendments_dir = repo / "docs" / "epics" / "2_active" / "_amendments"
    if amendments_dir.is_dir():
        for candidate in sorted(amendments_dir.glob("*.md")):
            if epic_tool_guard(candidate, "read", epic_id=epic_id, root=repo):
                paths.append(candidate.resolve())

    return _dedupe_paths(paths)


def collect_feature_readable_paths(feature_id: str, *, root: Path) -> list[Path]:
    repo = Path(root).resolve()
    feature = read_doc(feature_id, root=repo)
    paths: list[Path] = [feature.meta.path.resolve()]

    parent_id = feature.meta.parent
    if parent_id is not None:
        parent = read_doc(parent_id, root=repo)
        if feature_tool_guard(parent.meta.path, "read", feature_id=feature_id, root=repo):
            paths.append(parent.meta.path.resolve())

    sidecar = (repo / "docs" / "_comments" / f"{feature_id}.jsonl").resolve()
    if sidecar.is_file() and feature_tool_guard(
        sidecar, "read", feature_id=feature_id, root=repo
    ):
        paths.append(sidecar)

    board = list_board(repo)
    for meta in board.by_id.values():
        if meta.tier != "task" or meta.parent != feature_id:
            continue
        if feature_tool_guard(meta.path, "read", feature_id=feature_id, root=repo):
            paths.append(meta.path.resolve())

    return _dedupe_paths(paths)


def collect_boss_readable_paths(*, root: Path) -> list[Path]:
    """Board work docs, supervisor config, and boss queue — not planning transcripts."""

    repo = Path(root).resolve()
    paths: list[Path] = []
    board = list_board(repo)
    for meta in board.by_id.values():
        paths.append(meta.path.resolve())

    cascade_toml = repo / "cascade.toml"
    if cascade_toml.is_file():
        paths.append(cascade_toml.resolve())

    boss_queue = repo / "docs" / "_queue" / "boss.jsonl"
    if boss_queue.is_file():
        paths.append(boss_queue.resolve())

    return _dedupe_paths(paths)


def materialize_scratch(
    repo_root: Path,
    readable_paths: list[Path],
    *,
    tier: PlanningTier,
) -> Path:
    """Copy allowed read paths into a fresh directory; return scratch root."""

    repo = Path(repo_root).resolve()
    scratch = Path(tempfile.mkdtemp(prefix="cascade_planning_"))
    for src in readable_paths:
        safe = _safe_materialize_source(repo, src)
        if safe is None:
            continue
        rel = safe.relative_to(repo)
        dest = scratch / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe, dest)

    if tier == "boss":
        from cascade.boss.view import compute_boss_view

        view = compute_boss_view(root=repo)
        view_path = scratch / "docs" / "_boss" / "view.json"
        view_path.parent.mkdir(parents=True, exist_ok=True)
        view_path.write_text(
            json.dumps(
                {
                    "dispatchable_features": view.dispatchable_features,
                    "dispatchable_tasks": view.dispatchable_tasks,
                    "slots_free": view.slots_free,
                    "failed_tasks": view.failed_tasks,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return scratch


def teardown_scratch(scratch_dir: Path) -> None:
    shutil.rmtree(scratch_dir, ignore_errors=True)


def _safe_materialize_source(repo: Path, src: Path) -> Path | None:
    """Return a repo-local regular file path, or skip symlinks and escapes."""

    if src.is_symlink():
        return None
    try:
        resolved = src.resolve(strict=False)
    except OSError:
        return None
    if resolved.is_symlink():
        return None
    try:
        resolved.relative_to(repo)
    except ValueError:
        return None
    if not resolved.is_file():
        return None
    return resolved


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered
