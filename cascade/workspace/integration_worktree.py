"""Stacked integration branches and worktrees (feat_014 / task_065)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from cascade.board.errors import GitError, NotFound
from cascade.board.gitutil import head_sha, path_for_work_id
from cascade.board.store import list_board
from cascade.board.types import BoardIndex, WorkMeta

IntegrationKind = Literal["epic", "feature", "task"]

_KIND_DIR = {"epic": "epic", "feature": "feat", "task": "task"}
_REGISTRY_NAME = "worktrees.json"


@dataclass(frozen=True)
class IntegrationWorktree:
    kind: IntegrationKind
    work_id: str
    branch: str
    path: Path
    base_sha: str


def integration_branch(kind: IntegrationKind, work_id: str) -> str:
    prefix = _KIND_DIR[kind]
    return f"{prefix}/{work_id}"


def integration_worktree_path(kind: IntegrationKind, work_id: str, *, trunk: Path) -> Path:
    """Absolute path under ``trunk/.cascade/worktrees/{epic|feat|task}_{id}``."""

    name = f"{_KIND_DIR[kind]}_{work_id}"
    return (trunk / ".cascade" / "worktrees" / name).resolve()


def registry_path(trunk: Path) -> Path:
    return (trunk / ".cascade" / _REGISTRY_NAME).resolve()


def locate_trunk(checkout: Path) -> Path:
    """Product trunk root for a trunk or integration worktree checkout."""

    path = checkout.resolve()
    if registry_path(path).is_file():
        return path
    parts = path.parts
    if ".cascade" in parts:
        index = parts.index(".cascade")
        return Path(*parts[:index])
    return path


def load_registry(trunk: Path) -> list[IntegrationWorktree]:
    """Load persisted worktrees. Idempotent with ``save_registry`` after each create."""

    path = registry_path(trunk)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return []
    result: list[IntegrationWorktree] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            kind = item["kind"]
            work_id = item["work_id"]
            branch = item["branch"]
            rel = item["path"]
            base_sha = item["base_sha"]
        except KeyError:
            continue
        if kind not in _KIND_DIR:
            continue
        wt_path = (trunk / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        result.append(
            IntegrationWorktree(
                kind=kind,  # type: ignore[arg-type]
                work_id=str(work_id),
                branch=str(branch),
                path=wt_path,
                base_sha=str(base_sha),
            )
        )
    return result


def save_registry(trunk: Path, entries: list[IntegrationWorktree]) -> None:
    trunk = trunk.resolve()
    path = registry_path(trunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "entries": [
            {
                **asdict(entry),
                "path": entry.path.relative_to(trunk).as_posix(),
            }
            for entry in entries
        ]
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def get_integration_worktree(
    trunk: Path,
    kind: IntegrationKind,
    work_id: str,
) -> IntegrationWorktree | None:
    for entry in load_registry(trunk):
        if entry.kind == kind and entry.work_id == work_id:
            return entry
    return None


def create_integration_worktree(
    kind: IntegrationKind,
    work_id: str,
    *,
    branch: str,
    base_ref: str,
    trunk: Path,
) -> IntegrationWorktree:
    """Add ``branch`` at ``base_ref`` and register a worktree (from trunk git dir)."""

    trunk = trunk.resolve()
    if head_sha(trunk) is None:
        raise GitError("cannot create integration worktree: repo has no commits")

    wt_path = integration_worktree_path(kind, work_id, trunk=trunk)
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    base_sha = _resolve_ref(trunk, base_ref)

    _remove_stale_worktree(trunk, wt_path)

    if _branch_exists(trunk, branch):
        _git(trunk, "worktree", "add", str(wt_path), branch)
    else:
        _git(trunk, "worktree", "add", "-b", branch, str(wt_path), base_ref)

    record = IntegrationWorktree(
        kind=kind,
        work_id=work_id,
        branch=branch,
        path=wt_path.resolve(),
        base_sha=base_sha,
    )
    entries = [e for e in load_registry(trunk) if not (e.kind == kind and e.work_id == work_id)]
    entries.append(record)
    save_registry(trunk, entries)
    return record


def ensure_integration_worktree(
    kind: IntegrationKind,
    work_id: str,
    *,
    branch: str,
    base_ref: str,
    trunk: Path,
) -> IntegrationWorktree:
    """Return an existing registration or create one."""

    existing = get_integration_worktree(trunk, kind, work_id)
    if existing is not None and existing.path.is_dir():
        return existing
    return create_integration_worktree(
        kind,
        work_id,
        branch=branch,
        base_ref=base_ref,
        trunk=trunk,
    )


def repair_missing_worktree(
    kind: IntegrationKind,
    work_id: str,
    *,
    trunk: Path,
) -> IntegrationWorktree | None:
    """Recreate the worktree directory from an existing branch; no dispatch event."""

    trunk = trunk.resolve()
    entry = get_integration_worktree(trunk, kind, work_id)
    if entry is None:
        branch = integration_branch(kind, work_id)
        if not _branch_exists(trunk, branch):
            return None
        wt_path = integration_worktree_path(kind, work_id, trunk=trunk)
        base_sha = _resolve_ref(trunk, branch)
        entry = IntegrationWorktree(
            kind=kind,
            work_id=work_id,
            branch=branch,
            path=wt_path,
            base_sha=base_sha,
        )
    if entry.path.is_dir():
        return entry
    if not _branch_exists(trunk, entry.branch):
        return None
    wt_path = entry.path
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    _remove_stale_worktree(trunk, wt_path)
    _git(trunk, "worktree", "add", str(wt_path), entry.branch)
    entries = [e for e in load_registry(trunk) if not (e.kind == kind and e.work_id == work_id)]
    entries.append(entry)
    save_registry(trunk, entries)
    return entry


def repair_all_registered(trunk: Path) -> list[IntegrationWorktree]:
    """Repair every registry entry whose directory is missing."""

    repaired: list[IntegrationWorktree] = []
    for entry in load_registry(trunk):
        fixed = repair_missing_worktree(entry.kind, entry.work_id, trunk=trunk)
        if fixed is not None:
            repaired.append(fixed)
    return repaired


def epic_brief_committed_on_trunk(work_id: str, *, trunk: Path) -> bool:
    """True when ``work_id`` epic markdown exists in git at trunk HEAD (narrow brief gate)."""

    if head_sha(trunk) is None:
        return False
    return path_for_work_id(trunk, "HEAD", work_id) is not None


def is_trunk_pointer(meta: WorkMeta) -> bool:
    return meta.tier == "epic" and meta.integration_branch is not None


def _boards_for_trunk(trunk: Path) -> list[BoardIndex]:
    """One board scan per checkout. Callers must not scan again per work id."""

    trunk = trunk.resolve()
    boards = [list_board(trunk)]
    for entry in load_registry(trunk):
        if entry.path.is_dir():
            boards.append(list_board(entry.path))
    return boards


def merged_board(trunk: Path) -> BoardIndex:
    """Supervisor view: trunk plus each registered integration worktree board."""

    by_id: dict[str, WorkMeta] = {}
    for board in _boards_for_trunk(trunk):
        for work_id, meta in board.by_id.items():
            current = by_id.get(work_id)
            if current is None or _meta_preference(meta) > _meta_preference(current):
                by_id[work_id] = meta
    return BoardIndex(by_id=by_id)


def doc_filesystem_root(work_id: str, *, trunk: Path) -> Path:
    """Return the checkout root that owns ``work_id``'s markdown file."""

    meta = _best_meta_for_id(work_id, trunk=trunk)
    return git_root_for_path(meta.path)


def _best_meta_for_id(work_id: str, *, trunk: Path) -> WorkMeta:
    meta = merged_board(trunk).by_id.get(work_id)
    if meta is None:
        raise NotFound(work_id)
    return meta


def _meta_preference(meta: WorkMeta) -> tuple[int, int, int]:
    if is_trunk_pointer(meta):
        return (-100, 0, 0)
    column_rank = {"2_active": 30, "3_completed": 20, "1_backlog": 10}
    col = column_rank.get(meta.path.parent.name, 0)
    path = meta.path.as_posix()
    owner_bonus = 0
    if meta.tier == "epic" and "/worktrees/epic_" in path:
        owner_bonus = 5
    if meta.tier == "feature" and "/worktrees/feat_" in path:
        owner_bonus = 5
    if meta.tier == "task" and "/worktrees/feat_" in path:
        owner_bonus = 5
    if meta.tier == "task" and "/worktrees/task_" in path:
        owner_bonus = -15
    if meta.tier == "feature" and "/worktrees/task_" in path:
        owner_bonus = -40
    return (col + owner_bonus, col, owner_bonus)


def scan_active_markdown_roots(trunk: Path) -> list[Path]:
    """Trunk plus integration worktrees for watchdog / resume scans."""

    roots = [trunk.resolve()]
    for entry in load_registry(trunk):
        if entry.path.is_dir():
            roots.append(entry.path.resolve())
    return roots


def git_root_for_path(path: Path) -> Path:
    """Resolve the worktree checkout root containing ``path``."""

    current = path.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise GitError(f"no git worktree root for {path}")


def _resolve_ref(trunk: Path, ref: str) -> str:
    result = _git(trunk, "rev-parse", ref, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git rev-parse {ref!r} failed")
    return result.stdout.strip()


def branch_exists(trunk: Path, branch: str) -> bool:
    result = _git(trunk, "show-ref", "--verify", f"refs/heads/{branch}", check=False)
    return result.returncode == 0


def _branch_exists(trunk: Path, branch: str) -> bool:
    return branch_exists(trunk, branch)


def _remove_stale_worktree(trunk: Path, worktree: Path) -> None:
    wt = worktree.resolve()
    listed = _git(trunk, "worktree", "list", "--porcelain", check=False)
    blocks = (listed.stdout or "").split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        path_line = next(
            (line[7:] for line in block.splitlines() if line.startswith("worktree ")),
            None,
        )
        if path_line is None:
            continue
        registered = Path(path_line).resolve()
        if registered != wt:
            continue
        _git(trunk, "worktree", "remove", "--force", str(registered), check=False)
        break
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    _git(trunk, "worktree", "prune", check=False)


def _env(trunk: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    git_dir = (trunk / ".git").resolve()
    env["GIT_DIR"] = str(git_dir)
    env["GIT_WORK_TREE"] = str(trunk.resolve())
    return env


def _git(trunk: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=trunk,
        env=_env(trunk),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git {' '.join(args)} failed")
    return result
