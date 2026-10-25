"""Read-only remote product-trunk backlog snapshot (feat_006 / task_014)."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.errors import GitError, SchemaError
from cascade.board.gitutil import _run as git_run, path_for_work_id, read_blob
from cascade.board.parse import parse_text
from cascade.board.paths import column_for_status
from cascade.board.store import list_board
from cascade.board.types import BoardIndex
from cascade.workspace.integration_worktree import invalidate_merged_board, load_registry

_SNAPSHOT_DIR = "backlog_snapshot"
_BACKLOG_PREFIX = "docs/epics/1_backlog/"
_BACKLOG_PATH = re.compile(
    r"^docs/epics/1_backlog/(epic_\d+)_[^/]+\.md$"
)


@dataclass(frozen=True)
class BacklogProvenance:
    sha: str
    remote: str
    trunk: str
    updated_at: str
    omitted_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class RefreshResult:
    sha: str
    unchanged: bool
    omitted_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]


def snapshot_root(trunk: Path) -> Path:
    return trunk.resolve() / ".cascade" / _SNAPSHOT_DIR


def read_provenance(trunk: Path) -> BacklogProvenance | None:
    path = snapshot_root(trunk) / "provenance.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        sha = str(raw["sha"])
        remote = str(raw["remote"])
        trunk_branch = str(raw["trunk"])
        updated_at = str(raw["updated_at"])
    except KeyError:
        return None
    omitted = tuple(str(item) for item in raw.get("omitted_ids") or [])
    diagnostics = tuple(str(item) for item in raw.get("diagnostics") or [])
    return BacklogProvenance(
        sha=sha,
        remote=remote,
        trunk=trunk_branch,
        updated_at=updated_at,
        omitted_ids=omitted,
        diagnostics=diagnostics,
    )


def snapshot_board(trunk: Path) -> BoardIndex:
    root = snapshot_root(trunk)
    docs = root / "docs"
    if not docs.is_dir():
        return BoardIndex(by_id={})
    return list_board(root)


def resolve_epic_brief_base_sha(work_id: str, *, trunk: Path) -> str | None:
    """Return the git revision that contains ``work_id``'s epic brief, if any."""

    trunk = trunk.resolve()
    # A merged backlog edit is represented by the managed snapshot until a
    # human activates it. Prefer that approved revision over a stale local
    # backlog checkout, while leaving live rows to their owning checkout.
    snapshot_sha = _approved_snapshot_sha(work_id, trunk=trunk)
    if snapshot_sha is not None:
        return snapshot_sha
    head = git_run(["rev-parse", "--verify", "-q", "HEAD"], trunk, check=False)
    if head.returncode == 0:
        local_sha = head.stdout.strip()
        if local_sha and path_for_work_id(trunk, local_sha, work_id) is not None:
            return local_sha
    provenance = read_provenance(trunk)
    if provenance is not None and path_for_work_id(trunk, provenance.sha, work_id) is not None:
        return provenance.sha
    return None


def is_snapshot_only_epic(work_id: str, *, trunk: Path) -> bool:
    """True when ``work_id`` is visible only from the managed backlog snapshot."""

    trunk = trunk.resolve()
    if work_id in list_board(trunk).by_id:
        return False
    return work_id in snapshot_board(trunk).by_id


def resolve_validated_epic_activation_sha(work_id: str, *, trunk: Path) -> str | None:
    """Resolve and validate the git revision to cut an epic integration branch from."""

    trunk = trunk.resolve()
    if is_snapshot_only_epic(work_id, trunk=trunk):
        provenance = read_provenance(trunk)
        if provenance is None:
            return None
        sha = provenance.sha
        if not _object_exists(trunk, sha):
            return None
        if path_for_work_id(trunk, sha, work_id) is None:
            return None
        return sha
    return resolve_epic_brief_base_sha(work_id, trunk=trunk)


def _approved_snapshot_sha(work_id: str, *, trunk: Path) -> str | None:
    """Return the current snapshot revision for an eligible backlog epic."""

    provenance = read_provenance(trunk)
    if provenance is None:
        return None
    snapshot_meta = snapshot_board(trunk).by_id.get(work_id)
    if snapshot_meta is None or snapshot_meta.tier != "epic":
        return None
    if snapshot_meta.path.parent.name != "1_backlog":
        return None
    # A snapshot must not become an activation source for a live integration
    # row. Import lazily to avoid the module cycle.
    from cascade.workspace.integration_worktree import merged_board

    current = merged_board(trunk).by_id.get(work_id)
    if current is not None and (
        current.status != "backlog" or current.path.parent.name != "1_backlog"
    ):
        return None
    if not _object_exists(trunk, provenance.sha):
        return None
    if path_for_work_id(trunk, provenance.sha, work_id) is None:
        return None
    return provenance.sha


def _object_exists(trunk: Path, sha: str) -> bool:
    result = git_run(["cat-file", "-e", f"{sha}^{{commit}}"], trunk, check=False)
    return result.returncode == 0


def refresh_remote_backlog_snapshot(
    trunk: Path,
    *,
    remote: str,
    trunk_branch: str,
) -> RefreshResult:
    """Fetch ``remote``/``trunk_branch`` and atomically publish backlog epic briefs."""

    trunk = trunk.resolve()
    remote_ref = f"{remote}/{trunk_branch}"
    fetch = git_run(["fetch", remote, trunk_branch], trunk, check=False)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout).strip()
        if "couldn't find remote ref" in detail or "could not find remote ref" in detail:
            raise GitError(
                f"{remote} has no branch {trunk_branch!r}; push or configure the product "
                "trunk before pulling briefs"
            )
        raise GitError(detail or "fetch failed")
    remote_sha = git_run(["rev-parse", f"{remote_ref}^{{commit}}"], trunk, check=False)
    if remote_sha.returncode != 0:
        raise GitError(
            (remote_sha.stderr or remote_sha.stdout).strip()
            or f"remote branch {remote_ref} is unavailable"
        )
    sha = remote_sha.stdout.strip()
    current = read_provenance(trunk)
    if current is not None and current.sha == sha:
        return RefreshResult(
            sha=sha,
            unchanged=True,
            omitted_ids=current.omitted_ids,
            diagnostics=current.diagnostics,
        )

    blobs = _load_remote_backlog_blobs(trunk, sha)
    local_epics = _local_supervisor_epic_ids(trunk)
    omitted: list[str] = []
    diagnostics: list[str] = []
    materialized: dict[str, str] = {}
    for rel, content in sorted(blobs.items()):
        match = _BACKLOG_PATH.match(rel)
        if match is None:
            continue
        epic_id = match.group(1)
        if epic_id in local_epics:
            omitted.append(epic_id)
            diagnostics.append(
                f"omitted {epic_id}: already present in the local supervisor board"
            )
            continue
        materialized[rel] = content

    _publish_snapshot(
        trunk,
        sha=sha,
        remote=remote,
        trunk_branch=trunk_branch,
        files=materialized,
        omitted_ids=tuple(sorted(set(omitted))),
        diagnostics=tuple(diagnostics),
    )
    invalidate_merged_board(trunk)
    return RefreshResult(
        sha=sha,
        unchanged=False,
        omitted_ids=tuple(sorted(set(omitted))),
        diagnostics=tuple(diagnostics),
    )


def _load_remote_backlog_blobs(trunk: Path, sha: str) -> dict[str, str]:
    listing = git_run(["ls-tree", "-r", "--name-only", sha], trunk, check=False)
    if listing.returncode != 0:
        detail = (listing.stderr or listing.stdout).strip()
        raise GitError(detail or f"git ls-tree {sha} failed")
    paths = [
        line
        for line in listing.stdout.splitlines()
        if line.startswith(_BACKLOG_PREFIX) and line.endswith(".md")
    ]
    by_id: dict[str, str] = {}
    blobs: dict[str, str] = {}
    for rel in paths:
        content = read_blob(trunk, sha, rel)
        try:
            doc = parse_text(content, trunk / rel)
        except SchemaError as exc:
            raise GitError(f"malformed remote brief at {rel}: {exc}") from exc
        meta = doc.meta
        if meta.tier != "epic":
            raise GitError(f"remote backlog file {rel} is not an epic brief")
        if column_for_status(meta.status) != "backlog":
            raise GitError(
                f"remote backlog file {rel} has status {meta.status!r}, expected backlog"
            )
        if meta.id in by_id:
            raise GitError(f"duplicate epic id {meta.id} in remote backlog")
        by_id[meta.id] = rel
        blobs[rel] = content
    return blobs


def _local_supervisor_epic_ids(trunk: Path) -> set[str]:
    ids: set[str] = set()
    roots = [trunk.resolve()]
    roots.extend(entry.path for entry in load_registry(trunk) if entry.path.is_dir())
    for root in roots:
        for meta in list_board(root).by_id.values():
            if meta.tier == "epic" and meta.status != "backlog":
                ids.add(meta.id)
    return ids


def _publish_snapshot(
    trunk: Path,
    *,
    sha: str,
    remote: str,
    trunk_branch: str,
    files: dict[str, str],
    omitted_ids: tuple[str, ...],
    diagnostics: tuple[str, ...],
) -> None:
    base = snapshot_root(trunk)
    staging = trunk / ".cascade" / f".{_SNAPSHOT_DIR}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for rel, content in files.items():
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    payload = {
        "sha": sha,
        "remote": remote,
        "trunk": trunk_branch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "omitted_ids": list(omitted_ids),
        "diagnostics": list(diagnostics),
    }
    provenance_path = staging / "provenance.json"
    provenance_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    backup = trunk / ".cascade" / f".{_SNAPSHOT_DIR}.backup"
    if backup.exists():
        shutil.rmtree(backup)

    had_base = base.exists()
    moved_base = False
    restored = False
    completed = False
    try:
        if had_base:
            os.replace(base, backup)
            moved_base = True
        os.replace(staging, base)
        completed = True
    except Exception:
        # Restore the last valid snapshot before surfacing the replacement error.
        if moved_base:
            if base.exists():
                shutil.rmtree(base)
            if backup.exists():
                os.replace(backup, base)
                restored = True
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists() and (completed or not moved_base or restored):
            shutil.rmtree(backup)


def remove_snapshot_for_tests(trunk: Path) -> None:
    """Drop the managed snapshot directory (tests only)."""

    path = snapshot_root(trunk)
    if path.exists():
        shutil.rmtree(path)
    invalidate_merged_board(trunk)
