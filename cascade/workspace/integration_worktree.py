"""Stacked integration branches and worktrees (feat_014 / task_065)."""

from __future__ import annotations

import contextvars
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Iterator, Literal

import fcntl

from cascade.board.errors import GitError, NotFound
from cascade.board.gitutil import head_sha, path_for_work_id
from cascade.board.store import list_board
from cascade.board.types import BoardIndex, WorkMeta

IntegrationKind = Literal["epic", "feature", "task"]

_KIND_DIR = {"epic": "epic", "feature": "feat", "task": "task"}
_REGISTRY_NAME = "worktrees.json"
_REGISTRY_LOCK_NAME = "worktrees.lock"
_MERGED_BOARD_CACHE_TTL_S = 2.0
_registry_thread_lock = threading.RLock()
_merged_board_cache_lock = threading.RLock()
_merged_board_cache: dict[Path, tuple[float, BoardIndex]] = {}
_board_snapshot: contextvars.ContextVar[tuple[Path, BoardIndex] | None] = (
    contextvars.ContextVar("_board_snapshot", default=None)
)


@dataclass(frozen=True)
class IntegrationWorktree:
    kind: IntegrationKind
    work_id: str
    branch: str
    path: Path
    base_sha: str


@dataclass(frozen=True)
class CancellationTeardownResult:
    """Outcome of deleting one work item's exactly-owned local artifacts."""

    complete: bool
    step: str
    detail: str | None = None


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


@contextmanager
def _locked_registry(trunk: Path) -> Iterator[None]:
    """Serialize registry access across threads and supervisor processes."""

    trunk = trunk.resolve()
    lock_path = trunk / ".cascade" / _REGISTRY_LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _registry_thread_lock:
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_registry_unlocked(trunk: Path) -> list[IntegrationWorktree]:
    """Load the registry while the caller owns ``_locked_registry``."""

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


def load_registry(trunk: Path) -> list[IntegrationWorktree]:
    """Load a complete persisted registry snapshot."""

    trunk = trunk.resolve()
    with _locked_registry(trunk):
        return _load_registry_unlocked(trunk)


def _save_registry_unlocked(trunk: Path, entries: list[IntegrationWorktree]) -> None:
    """Atomically publish ``entries`` while the caller owns the registry lock."""

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
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def save_registry(trunk: Path, entries: list[IntegrationWorktree]) -> None:
    """Atomically replace the persisted integration-worktree registry."""

    trunk = trunk.resolve()
    with _locked_registry(trunk):
        _save_registry_unlocked(trunk, entries)
    # Keep cache locking outside the registry critical section: merged_board
    # acquires these locks in the opposite direction while building a snapshot.
    invalidate_merged_board(trunk)


def _mutate_registry(
    trunk: Path,
    mutation: Callable[[list[IntegrationWorktree]], list[IntegrationWorktree]],
) -> None:
    """Apply one read-modify-write transaction without losing concurrent rows."""

    trunk = trunk.resolve()
    with _locked_registry(trunk):
        entries = _load_registry_unlocked(trunk)
        _save_registry_unlocked(trunk, mutation(entries))
    invalidate_merged_board(trunk)


def _upsert_registry_entry(trunk: Path, entry: IntegrationWorktree) -> None:
    def upsert(entries: list[IntegrationWorktree]) -> list[IntegrationWorktree]:
        kept = [
            candidate
            for candidate in entries
            if not (candidate.kind == entry.kind and candidate.work_id == entry.work_id)
        ]
        kept.append(entry)
        return kept

    _mutate_registry(trunk, upsert)


def _remove_registry_entry(trunk: Path, kind: IntegrationKind, work_id: str) -> None:
    _mutate_registry(
        trunk,
        lambda entries: [
            candidate
            for candidate in entries
            if not (candidate.kind == kind and candidate.work_id == work_id)
        ],
    )


def get_integration_worktree(
    trunk: Path,
    kind: IntegrationKind,
    work_id: str,
) -> IntegrationWorktree | None:
    for entry in load_registry(trunk):
        if entry.kind == kind and entry.work_id == work_id:
            return entry
    return None


def cancel_integration_worktree(
    kind: IntegrationKind,
    work_id: str,
    *,
    trunk: Path,
    discard_uncommitted: bool = False,
) -> CancellationTeardownResult:
    """Delete the exact registered checkout and branch owned by ``work_id``.

    Cancellation may discard a clean unmerged owned branch. It never forces a
    dirty checkout, follows an arbitrary registry path, or derives a deletion
    target from user-controlled metadata. Completed steps are safe to retry.
    """

    trunk = locate_trunk(trunk).resolve()
    entry = get_integration_worktree(trunk, kind, work_id)
    expected_branch = integration_branch(kind, work_id)
    expected_path = integration_worktree_path(kind, work_id, trunk=trunk)
    if entry is None:
        # A matching-looking branch without a registry row is not proven owned.
        return CancellationTeardownResult(True, "complete")
    if entry is not None:
        if entry.branch != expected_branch or entry.path.resolve() != expected_path:
            return CancellationTeardownResult(
                False,
                "verify_ownership",
                f"registered artifacts do not match owned {expected_branch} at {expected_path}",
            )
        present, locked = _listed_worktree_state(trunk, entry.path)
        if locked:
            return CancellationTeardownResult(
                False, "remove_worktree", "owned worktree is locked"
            )
        try:
            Path.cwd().resolve().relative_to(entry.path.resolve())
        except ValueError:
            pass
        else:
            return CancellationTeardownResult(
                False, "remove_worktree", "cannot remove the current working directory"
            )
        if entry.path.exists():
            status = _git(
                entry.path, "status", "--porcelain", "--untracked-files=all", check=False
            )
            if status.returncode != 0:
                return CancellationTeardownResult(
                    False, "inspect_worktree", (status.stderr or status.stdout).strip()
                )
            if status.stdout.strip() and not discard_uncommitted:
                return CancellationTeardownResult(
                    False,
                    "remove_worktree",
                    f"owned worktree has uncommitted changes: {entry.path}; retry with "
                    "discard_uncommitted=True to confirm discard for this cancellation",
                )
            remove_args = ["worktree", "remove"]
            if discard_uncommitted:
                remove_args.append("--force")
            remove_args.append(str(entry.path))
            removed = _git(trunk, *remove_args, check=False)
            if removed.returncode != 0:
                return CancellationTeardownResult(
                    False, "remove_worktree", (removed.stderr or removed.stdout).strip()
                )
        elif present:
            _git(trunk, "worktree", "prune", check=False)
            if _listed_worktree_state(trunk, entry.path)[0]:
                return CancellationTeardownResult(
                    False,
                    "remove_worktree",
                    "stale worktree registration could not be pruned",
                )
    branch = _git(
        trunk, "show-ref", "--verify", f"refs/heads/{expected_branch}", check=False
    )
    if branch.returncode == 0:
        deleted = _git(trunk, "branch", "-D", expected_branch, check=False)
        if deleted.returncode != 0:
            return CancellationTeardownResult(
                False, "delete_branch", (deleted.stderr or deleted.stdout).strip()
            )
    _remove_registry_entry(trunk, kind, work_id)
    return CancellationTeardownResult(True, "complete")


def retire_integration_worktree(
    kind: IntegrationKind,
    work_id: str,
    *,
    merged_into: str,
    merge_confirmed: bool = False,
    trunk: Path,
) -> bool:
    """Remove a terminal integration checkout without deleting its branch.

    Retirement is deliberately conservative: the registered path must be the
    canonical Cascade path, and a present checkout must be clean, unlocked, and
    not contain this process's current directory.  Normally the integration
    branch must also be reachable from ``merged_into``.  ``merge_confirmed`` is
    reserved for an authoritative forge "merged" result, where squash/rebase
    merging intentionally makes ancestry unavailable.  Failed safety checks
    leave both the checkout and registry entry intact so recovery remains possible.
    """

    trunk = locate_trunk(trunk).resolve()
    entry = get_integration_worktree(trunk, kind, work_id)
    if entry is None:
        return True
    expected = integration_worktree_path(kind, work_id, trunk=trunk)
    if entry.path.resolve() != expected:
        return False
    if not merge_confirmed and not _branch_merged_into(trunk, entry.branch, merged_into):
        return False

    present, locked = _listed_worktree_state(trunk, entry.path)
    if locked:
        return False
    try:
        Path.cwd().resolve().relative_to(entry.path.resolve())
    except ValueError:
        pass
    else:
        return False

    if entry.path.exists():
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=entry.path,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if status.returncode != 0 or status.stdout.strip():
            return False
        removed = _git(
            trunk, "worktree", "remove", str(entry.path), check=False
        )
        if removed.returncode != 0:
            return False
    elif present:
        _git(trunk, "worktree", "prune", check=False)
        still_present, _ = _listed_worktree_state(trunk, entry.path)
        if still_present:
            return False

    _remove_registry_entry(trunk, kind, work_id)
    return True


def unregister_missing_integration_worktree(
    kind: IntegrationKind, work_id: str, *, trunk: Path
) -> bool:
    """Drop a stale registry row only after its checkout is absent from disk and Git."""

    trunk = locate_trunk(trunk).resolve()
    entry = get_integration_worktree(trunk, kind, work_id)
    if entry is None:
        return True
    if entry.path.resolve() != integration_worktree_path(kind, work_id, trunk=trunk):
        return False
    present, _ = _listed_worktree_state(trunk, entry.path)
    if entry.path.exists() or present:
        return False
    _remove_registry_entry(trunk, kind, work_id)
    return True


def terminal_doc_persisted_outside_worktree(
    kind: IntegrationKind, work_id: str, *, trunk: Path
) -> bool:
    """True when another checkout durably owns the terminal plan document.

    A merge confirmation proves that source changes landed, but it does not by
    itself prove that the completed plan is present in the destination checkout.
    Keep the source worktree registered until that metadata is visible elsewhere;
    otherwise removing it can make dependency resolution forget the completed
    work item entirely.
    """

    trunk = locate_trunk(trunk).resolve()
    source = get_integration_worktree(trunk, kind, work_id)
    if source is None:
        return True
    source_path = source.path.resolve()
    roots = [trunk]
    roots.extend(entry.path for entry in load_registry(trunk))
    for root in roots:
        resolved = root.resolve()
        if resolved == source_path or not resolved.is_dir():
            continue
        meta = list_board(resolved).by_id.get(work_id)
        if (
            meta is not None
            and meta.tier == kind
            and meta.status == "completed"
            and meta.path.parent.name == "3_completed"
        ):
            return True
    return False


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
    _upsert_registry_entry(trunk, record)
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
    _upsert_registry_entry(trunk, entry)
    return entry


def repair_all_registered(trunk: Path) -> list[IntegrationWorktree]:
    """Repair every registry entry whose directory is missing."""

    repaired: list[IntegrationWorktree] = []
    for entry in load_registry(trunk):
        fixed = repair_missing_worktree(entry.kind, entry.work_id, trunk=trunk)
        if fixed is not None:
            repaired.append(fixed)
    return repaired


def retire_terminal_registered_worktrees(trunk: Path) -> list[IntegrationWorktree]:
    """Reconcile stale registrations from durable completed lifecycle state.

    This runs before startup repair so a prior process crash cannot cause old
    terminal checkouts to be recreated forever.  Local merge ancestry proves
    task/epic completion.  A closed durable review record additionally proves a
    feature forge merge whose squash/rebase strategy erased source ancestry.
    """

    trunk = locate_trunk(trunk).resolve()
    board = merged_board(trunk)
    entries = load_registry(trunk)
    terminal_owners: dict[str, set[Path]] = {}
    for checkout in [trunk, *(entry.path for entry in entries)]:
        resolved = checkout.resolve()
        if not resolved.is_dir():
            continue
        for candidate in list_board(resolved).by_id.values():
            if (
                candidate.status == "completed"
                and candidate.path.parent.name == "3_completed"
            ):
                terminal_owners.setdefault(candidate.id, set()).add(resolved)
    closed_reviews: set[str] = set()
    review_path = trunk / ".cascade" / "reviews.json"
    if review_path.is_file():
        try:
            review_rows = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            review_rows = {}
        if isinstance(review_rows, dict):
            closed_reviews = {
                str(work_id)
                for work_id, record in review_rows.items()
                if isinstance(record, dict) and record.get("closed") is True
            }

    retired: list[IntegrationWorktree] = []
    for entry in entries:
        meta = board.by_id.get(entry.work_id)
        if (
            meta is None
            or meta.tier != entry.kind
            or meta.status != "completed"
            or meta.path.parent.name != "3_completed"
        ):
            continue
        if not any(
            owner != entry.path.resolve()
            for owner in terminal_owners.get(entry.work_id, set())
        ):
            continue
        if entry.kind == "epic":
            target = "HEAD"
            confirmed = False
        else:
            if not meta.parent:
                continue
            target_kind = "epic" if entry.kind == "feature" else "feat"
            target = f"{target_kind}/{meta.parent}"
            confirmed = entry.kind == "feature" and entry.work_id in closed_reviews
            if entry.kind == "feature" and not confirmed:
                from cascade.boss.rollup import feature_completed_recorded

                confirmed = feature_completed_recorded(
                    entry.work_id, meta.parent, root=trunk
                )
        if retire_integration_worktree(
            entry.kind,
            entry.work_id,
            merged_into=target,
            merge_confirmed=confirmed,
            trunk=trunk,
        ):
            retired.append(entry)
    return retired


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


def invalidate_merged_board(trunk: Path) -> None:
    """Drop the shared supervisor-board snapshot after a board or registry write."""

    with _merged_board_cache_lock:
        _merged_board_cache.pop(locate_trunk(trunk).resolve(), None)


def merged_board(trunk: Path) -> BoardIndex:
    """Return a short-lived, single-flight supervisor board snapshot.

    War Room and watchdog readers frequently ask for the same view concurrently.
    Serializing a cache miss means only one of them reparses all registered
    checkouts; waiters reuse that completed scan.
    """

    trunk = locate_trunk(trunk).resolve()
    snapshot = _board_snapshot.get()
    if snapshot is not None and snapshot[0] == trunk:
        return snapshot[1]
    now = time.monotonic()
    with _merged_board_cache_lock:
        cached = _merged_board_cache.get(trunk)
        if cached is not None and cached[0] > now:
            return cached[1]
        board = _merged_board_uncached(trunk)
        _merged_board_cache[trunk] = (time.monotonic() + _MERGED_BOARD_CACHE_TTL_S, board)
        return board


@contextmanager
def merged_board_snapshot(trunk: Path, board: BoardIndex) -> Iterator[None]:
    """Reuse one board view during a read-only response on this context."""

    token = _board_snapshot.set((locate_trunk(trunk).resolve(), board))
    try:
        yield
    finally:
        _board_snapshot.reset(token)


def _merged_board_uncached(trunk: Path) -> BoardIndex:
    """Build the supervisor view from trunk and registered worktrees."""

    trunk = trunk.resolve()
    boards = _boards_for_trunk(trunk)
    trunk_board = boards[0]
    completed_trunk_epics = {
        work_id: meta
        for work_id, meta in trunk_board.by_id.items()
        if meta.tier == "epic"
        and meta.status == "completed"
        and meta.path.parent.name == "3_completed"
        and not is_trunk_pointer(meta)
    }
    by_id: dict[str, WorkMeta] = {}
    # Approvals are monotonic decisions. A newer integration checkout can carry
    # an older copy of the plan, so its preferred path/status must not erase an
    # approval already written in another checkout (often the product trunk).
    approvals = {}
    plan_approvals = {}
    for board in boards:
        for work_id, meta in board.by_id.items():
            if meta.tier == "feature" and meta.approved_at is not None:
                approvals.setdefault(work_id, meta.approved_at)
            if meta.tier == "epic" and meta.plan_approved_at is not None:
                plan_approvals.setdefault(work_id, meta.plan_approved_at)
            if work_id in completed_trunk_epics:
                # Closing an epic makes the product-trunk document authoritative.
                # Registered worktrees are retained for history/recovery and can
                # still contain an active snapshot of the same epic.
                by_id[work_id] = completed_trunk_epics[work_id]
                continue
            current = by_id.get(work_id)
            if current is None or _meta_preference(meta) > _meta_preference(current):
                by_id[work_id] = meta
    for work_id, approved_at in approvals.items():
        if work_id in by_id:
            by_id[work_id] = replace(by_id[work_id], approved_at=approved_at)
    for work_id, approved_at in plan_approvals.items():
        if work_id in by_id:
            by_id[work_id] = replace(by_id[work_id], plan_approved_at=approved_at)
    from cascade.workspace.backlog_snapshot import read_provenance, snapshot_board

    if read_provenance(trunk) is not None:
        for work_id, meta in snapshot_board(trunk).by_id.items():
            if meta.tier != "epic" or meta.path.parent.name != "1_backlog":
                continue
            current = by_id.get(work_id)
            if current is None or (
                current.tier == "epic"
                and current.status == "backlog"
                and current.path.parent.name == "1_backlog"
            ):
                # The approved snapshot supersedes only a stale backlog copy.
                # Active/completed rows and integration worktrees stay live.
                by_id[work_id] = meta
    return BoardIndex(by_id=by_id)


def doc_filesystem_root(work_id: str, *, trunk: Path) -> Path:
    """Return the checkout root that owns ``work_id``'s markdown file."""

    meta = _best_meta_for_id(work_id, trunk=trunk)
    path = meta.path.resolve()
    from cascade.workspace.backlog_snapshot import snapshot_root

    snap = snapshot_root(trunk).resolve()
    try:
        path.relative_to(snap)
    except ValueError:
        return git_root_for_path(meta.path)
    return snap


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
        # A remotely accepted close can finish in the integration checkout
        # while the operator trunk has a stale, dirty active copy.  Keep that
        # terminal state visible until the operator checkout catches up.
        owner_bonus = 15 if meta.status == "completed" else 5
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


def _branch_merged_into(trunk: Path, branch: str, target: str) -> bool:
    if not _branch_exists(trunk, branch):
        return False
    target_exists = _git(trunk, "rev-parse", "--verify", target, check=False)
    if target_exists.returncode != 0:
        return False
    result = _git(
        trunk, "merge-base", "--is-ancestor", branch, target, check=False
    )
    return result.returncode == 0


def _listed_worktree_state(trunk: Path, worktree: Path) -> tuple[bool, bool]:
    """Return ``(registered_with_git, locked)`` for an exact worktree path."""

    listed = _git(trunk, "worktree", "list", "--porcelain", check=False)
    for block in (listed.stdout or "").split("\n\n"):
        lines = block.splitlines()
        path_line = next(
            (line[9:] for line in lines if line.startswith("worktree ")), None
        )
        if path_line is None or Path(path_line).resolve() != worktree.resolve():
            continue
        return True, any(line == "locked" or line.startswith("locked ") for line in lines)
    return False, False


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
