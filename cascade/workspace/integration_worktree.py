"""Stacked integration branches and worktrees (feat_014 / task_065)."""

from __future__ import annotations

import contextvars
import copy
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
from cascade.workspace.errors import MutationOwnerError
from cascade.board.gitutil import head_sha, path_for_work_id
from cascade.board.parse import parse_doc
from cascade.board.paths import column_dir
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


@dataclass(frozen=True)
class TerminalRetirementProof:
    """Inspectable, retry-safe proof required before a checkout is retired."""

    ok: bool
    reason: str | None = None
    next_action: str | None = None
    required_descendants: tuple[str, ...] = ()
    persisted_descendants: tuple[str, ...] = ()


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


def load_registry_readonly(trunk: Path) -> list[IntegrationWorktree]:
    """Read the registry without creating a lock file on a healthy audit."""

    trunk = trunk.resolve()
    lock_path = trunk / ".cascade" / _REGISTRY_LOCK_NAME
    with _registry_thread_lock:
        if not lock_path.exists():
            # Registry publication replaces its JSON file atomically. A writer
            # that creates the lock concurrently cannot expose a partial read.
            return _load_registry_unlocked(trunk)
        with lock_path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                return _load_registry_unlocked(trunk)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        if kind in {"epic", "feature"}:
            from cascade.war_room.chat_store import (
                TranscriptPendingError,
                resume_transcript_room_move,
            )

            try:
                resume_transcript_room_move(work_id, root=trunk)
            except TranscriptPendingError:
                return False
        return True
    expected = integration_worktree_path(kind, work_id, trunk=trunk)
    if entry.path.resolve() != expected or entry.branch != integration_branch(
        kind, work_id
    ):
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
        cached = _git(entry.path, "diff", "--cached", "--quiet", "HEAD", check=False)
        tracked = _git(entry.path, "diff", "--quiet", "HEAD", check=False)
        untracked = _git(
            entry.path, "ls-files", "--others", "--exclude-standard", check=False
        )
        untracked_source = [
            path
            for path in untracked.stdout.splitlines()
            if path
            and not path.startswith(
                (".cascade/", "docs/_queue/", "docs/_comments/", "docs/_war_room/")
            )
        ]
        if (
            cached.returncode != 0
            or tracked.returncode != 0
            or untracked.returncode != 0
            or untracked_source
        ):
            return False

    proof = prove_terminal_retirement(kind, work_id, trunk=trunk)
    if not proof.ok:
        return False

    def remove_checkout_and_registration() -> None:
        if entry.path.exists():
            removed = _git(trunk, "worktree", "remove", str(entry.path), check=False)
            if removed.returncode != 0:
                raise RuntimeError((removed.stderr or removed.stdout).strip())
        elif present:
            _git(trunk, "worktree", "prune", check=False)
            still_present, _ = _listed_worktree_state(trunk, entry.path)
            if still_present:
                raise RuntimeError("stale worktree registration could not be pruned")
        _remove_registry_entry(trunk, kind, work_id)

    if kind in {"epic", "feature"}:
        if kind == "epic":
            destination = trunk
        else:
            owned = list_board(entry.path).by_id.get(work_id)
            parent_entry = (
                get_integration_worktree(trunk, "epic", owned.parent)
                if owned is not None and owned.parent
                else None
            )
            destination = parent_entry.path if parent_entry is not None else trunk
        from cascade.war_room.chat_store import (
            TranscriptPendingError,
            move_transcript_room,
        )

        try:
            move_transcript_room(
                work_id,
                source_root=entry.path,
                destination_root=destination,
                root=trunk,
                switch_owner=remove_checkout_and_registration,
            )
        except (RuntimeError, TranscriptPendingError):
            return False
    else:
        try:
            remove_checkout_and_registration()
        except RuntimeError:
            return False
    return True


def unregister_missing_integration_worktree(
    kind: IntegrationKind, work_id: str, *, trunk: Path, require_missing_branch: bool = False
) -> bool:
    """Drop a stale registry row only after its checkout is absent from disk and Git."""

    trunk = locate_trunk(trunk).resolve()
    entry = get_integration_worktree(trunk, kind, work_id)
    if entry is None:
        return True
    if entry.path.resolve() != integration_worktree_path(kind, work_id, trunk=trunk):
        return False
    if require_missing_branch:
        if entry.branch != integration_branch(kind, work_id):
            return False
        branch = _git(trunk, "show-ref", "--verify", "--quiet", f"refs/heads/{entry.branch}", check=False)
        if branch.returncode != 1:
            return False
    present, _ = _listed_worktree_state(trunk, entry.path)
    if entry.path.exists() or present:
        return False
    _remove_registry_entry(trunk, kind, work_id)
    return True


def terminal_doc_persisted_outside_worktree(
    kind: IntegrationKind, work_id: str, *, trunk: Path
) -> bool:
    """Compatibility predicate backed by the descendant-aware proof."""

    return prove_terminal_retirement(kind, work_id, trunk=trunk).ok


def prove_terminal_retirement(
    kind: IntegrationKind, work_id: str, *, trunk: Path
) -> TerminalRetirementProof:
    """Persist and verify terminal descendants before retiring ``work_id``.

    The registered checkout remains the source of the terminal closure.  Its
    parent owner is the authorized destination.  Missing records are copied one
    at a time through the ordinary Git-backed board store, making an interrupted
    pass safe to repeat.  Existing nonterminal or conflicting destination rows
    are never overwritten.
    """

    from cascade.board.context import resolve_tracking_root
    from cascade.board.store import write_doc

    product = locate_trunk(trunk).resolve()
    entry = get_integration_worktree(product, kind, work_id)
    if entry is None:
        return TerminalRetirementProof(True)
    expected_path = integration_worktree_path(kind, work_id, trunk=product)
    expected_branch = integration_branch(kind, work_id)
    if entry.path.resolve() != expected_path or entry.branch != expected_branch:
        return TerminalRetirementProof(
            False,
            f"registered identity for {work_id} is noncanonical",
            f"repair the registry to {expected_branch} at {expected_path}",
        )
    present, locked = _listed_worktree_state(product, entry.path)
    if locked:
        return TerminalRetirementProof(
            False,
            f"registered checkout for {work_id} is locked",
            f"unlock {entry.path} after confirming its owner has stopped",
        )
    try:
        Path.cwd().resolve().relative_to(entry.path.resolve())
    except ValueError:
        pass
    else:
        return TerminalRetirementProof(
            False,
            f"registered checkout for {work_id} is currently occupied",
            "leave the checkout before retrying retirement",
        )
    if not present or not entry.path.is_dir():
        return TerminalRetirementProof(
            False,
            f"registered checkout for {work_id} is missing",
            "repair the exact registered checkout before retirement",
        )
    status = _git(
        entry.path, "status", "--porcelain", "--untracked-files=all", check=False
    )
    if status.returncode != 0 or status.stdout.strip():
        return TerminalRetirementProof(
            False,
            f"registered checkout for {work_id} is dirty or unreadable",
            f"finish or reconcile owner changes in {entry.path} before retirement",
        )
    try:
        source_root = resolve_mutation_owner(work_id, trunk=product, tier=kind)
    except MutationOwnerError as exc:
        return TerminalRetirementProof(False, exc.reason, exc.action)
    source_board = list_board(source_root)
    parent = source_board.by_id.get(work_id)
    if not _terminal_meta(parent, kind):
        return TerminalRetirementProof(
            False,
            f"terminal source document for {work_id} is missing or noncanonical",
            "restore the completed document in its exact registered owner",
        )

    try:
        if parent.parent:
            destination = resolve_mutation_owner(parent.parent, trunk=product)
        else:
            destination = locate_trunk(resolve_tracking_root(product)).resolve()
    except MutationOwnerError as exc:
        return TerminalRetirementProof(False, exc.reason, exc.action)
    destination = destination.resolve()
    if destination == entry.path.resolve():
        return TerminalRetirementProof(
            False,
            f"{work_id} has no distinct authorized terminal destination",
            "merge the parent checkout and persist its terminal document before retirement",
        )

    destination_parent = list_board(destination).by_id.get(work_id)
    if not _terminal_meta(destination_parent, kind):
        return TerminalRetirementProof(
            False,
            f"authorized destination lacks terminal document {work_id}",
            f"persist completed {work_id} in {destination} before retirement",
        )
    parent_provenance = _registered_parent_proven(
        kind,
        work_id,
        parent.parent,
        product=product,
        evidence_roots=(product, source_root, destination),
    )
    if parent_provenance is not None:
        return TerminalRetirementProof(
            False, parent_provenance[0], parent_provenance[1]
        )

    closure, refusal = _required_terminal_descendants(parent, source_board)
    if refusal is not None:
        return TerminalRetirementProof(False, refusal[0], refusal[1])
    required = tuple(meta.id for meta in closure)
    provenance_refusal = _terminal_provenance_refusal(
        ([parent] if kind == "task" else []) + closure,
        product=product,
        evidence_roots=(product, source_root, destination),
    )
    if provenance_refusal is not None:
        return TerminalRetirementProof(
            False, provenance_refusal[0], provenance_refusal[1], required
        )

    persisted: list[str] = []
    try:
        for meta in closure:
            destination_meta = list_board(destination).by_id.get(meta.id)
            if destination_meta is not None:
                if not _terminal_meta(destination_meta, meta.tier) or (
                    destination_meta.parent != meta.parent
                ):
                    return TerminalRetirementProof(
                        False,
                        f"authorized destination has conflicting record {meta.id}",
                        f"reconcile {meta.id} in {destination} without overwriting its provenance",
                        required,
                        tuple(persisted),
                    )
                continue
            doc = copy.deepcopy(parse_doc(meta.path))
            doc.sha = None
            doc.meta.status = "completed"
            doc.meta.path = (
                destination / column_dir(doc.meta.tier, "completed") / meta.path.name
            ).resolve()
            write_doc(doc, root=destination)
            persisted.append(meta.id)
    except Exception as exc:
        return TerminalRetirementProof(
            False,
            f"terminal descendant persistence was interrupted: {exc}",
            "retry retirement; already committed descendant records will be reused",
            required,
            tuple(persisted),
        )

    reread = list_board(destination)
    for meta in closure:
        copied = reread.by_id.get(meta.id)
        if not _terminal_meta(copied, meta.tier) or copied.parent != meta.parent:
            return TerminalRetirementProof(
                False,
                f"canonical readback is missing terminal descendant {meta.id}",
                f"restore completed {meta.id} in {destination} and retry",
                required,
                tuple(persisted),
            )
    return TerminalRetirementProof(
        True,
        required_descendants=required,
        persisted_descendants=tuple(persisted),
    )


def _terminal_meta(meta: WorkMeta | None, tier: str) -> bool:
    return bool(
        meta is not None
        and meta.tier == tier
        and meta.status == "completed"
        and meta.path.parent.name == "3_completed"
    )


def _required_terminal_descendants(
    parent: WorkMeta, board: BoardIndex
) -> tuple[list[WorkMeta], tuple[str, str] | None]:
    """Return the declared/reverse-linked descendant closure, parents first."""

    children_by_parent: dict[str, set[str]] = {}
    for meta in board.by_id.values():
        if meta.parent:
            children_by_parent.setdefault(meta.parent, set()).add(meta.id)
    pending = list(
        dict.fromkeys(
            [*parent.children, *sorted(children_by_parent.get(parent.id, set()))]
        )
    )
    result: list[WorkMeta] = []
    seen: set[str] = set()
    while pending:
        child_id = pending.pop(0)
        if child_id in seen:
            continue
        seen.add(child_id)
        child = board.by_id.get(child_id)
        if child is None:
            return [], (
                f"required descendant {child_id} is missing from {parent.id}'s registered owner",
                f"restore {child_id} in the registered checkout before retirement",
            )
        if child.parent != parent.id and not any(
            row.id == child.parent for row in result
        ):
            return [], (
                f"required descendant {child_id} has ambiguous parent lineage",
                f"reconcile the parent of {child_id} before retirement",
            )
        if not _terminal_meta(child, child.tier):
            return [], (
                f"required descendant {child_id} is not canonically terminal",
                f"complete {child_id} in its owning checkout before retirement",
            )
        result.append(child)
        pending.extend(child.children)
        pending.extend(sorted(children_by_parent.get(child.id, set())))
    return result, None


def _terminal_provenance_refusal(
    descendants: list[WorkMeta], *, product: Path, evidence_roots: tuple[Path, ...]
) -> tuple[str, str] | None:
    reviews = _review_records(product)
    for meta in descendants:
        if not meta.parent:
            return (
                f"terminal descendant {meta.id} lacks parent provenance",
                f"restore the parent of {meta.id} before retirement",
            )
        if meta.tier == "task":
            target = f"feat/{meta.parent}"
            proven = _branch_merged_into(
                product, integration_branch("task", meta.id), target
            )
            event_type = "TaskMerged"
            payload_key = "task_id"
        elif meta.tier == "feature":
            review = reviews.get(meta.id)
            if isinstance(review, dict) and review.get("closed") is not True:
                return (
                    f"feature review obligation for {meta.id} is unresolved",
                    f"complete or reconcile the review for {meta.id} before retirement",
                )
            target = f"epic/{meta.parent}"
            proven = _branch_merged_into(
                product, integration_branch("feature", meta.id), target
            )
            proven = proven or _closed_review_matches(review, target)
            event_type = "FeatureCompleted"
            payload_key = "feature_id"
        else:
            return (
                f"unsupported terminal descendant tier {meta.tier!r} for {meta.id}",
                "repair the descendant tier before retirement",
            )
        if not proven:
            proven = any(
                _completion_event_exists(
                    root, meta.parent, event_type, payload_key, meta.id
                )
                for root in evidence_roots
            )
        if not proven:
            return (
                f"terminal descendant {meta.id} lacks delivery/completion provenance",
                f"restore merge or completion evidence for {meta.id} before retirement",
            )
    return None


def _registered_parent_proven(
    kind: IntegrationKind,
    work_id: str,
    parent_id: str | None,
    *,
    product: Path,
    evidence_roots: tuple[Path, ...],
) -> tuple[str, str] | None:
    branch = integration_branch(kind, work_id)
    if kind == "epic":
        proven = _branch_merged_into(product, branch, "HEAD")
    elif parent_id is None:
        proven = False
    elif kind == "task":
        proven = _branch_merged_into(product, branch, f"feat/{parent_id}")
        proven = proven or any(
            _completion_event_exists(root, parent_id, "TaskMerged", "task_id", work_id)
            for root in evidence_roots
        )
    else:
        review = _review_records(product).get(work_id)
        if isinstance(review, dict) and review.get("closed") is not True:
            return (
                f"feature review obligation for {work_id} is unresolved",
                f"complete or reconcile the review for {work_id} before retirement",
            )
        target = f"epic/{parent_id}"
        proven = _branch_merged_into(product, branch, target)
        proven = proven or _closed_review_matches(review, target)
        proven = proven or any(
            _completion_event_exists(
                root, parent_id, "FeatureCompleted", "feature_id", work_id
            )
            for root in evidence_roots
        )
    if proven:
        return None
    return (
        f"registered source {work_id} lacks merge/completion provenance",
        f"merge or reconcile {branch} before retirement",
    )


def _review_records(product: Path) -> dict[str, object]:
    path = product / ".cascade" / "reviews.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _closed_review_matches(review: object, target: str) -> bool:
    return bool(
        isinstance(review, dict)
        and review.get("closed") is True
        and review.get("target_branch") == target
    )


def _completion_event_exists(
    root: Path, destination: str, event_type: str, payload_key: str, work_id: str
) -> bool:
    from cascade.watchdog.events import read_events

    events, _ = read_events(destination, 0, root=root)
    return any(
        event.type == event_type and event.payload.get(payload_key) == work_id
        for event in events
    )


def create_integration_worktree(
    kind: IntegrationKind,
    work_id: str,
    *,
    branch: str,
    base_ref: str,
    trunk: Path,
    prepare: Callable[[Path], None] | None = None,
) -> IntegrationWorktree:
    """Add a worktree, prepare its checkout if needed, then publish its registration."""

    trunk = trunk.resolve()
    if head_sha(trunk) is None:
        raise GitError("cannot create integration worktree: repo has no commits")

    source_room_root: Path | None = None
    if kind in {"epic", "feature"}:
        from cascade.war_room.chat_store import _chat_read_path

        source_room_root = _chat_read_path(work_id, root=trunk).parents[3]

    wt_path = integration_worktree_path(kind, work_id, trunk=trunk)
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    base_sha = _resolve_ref(trunk, base_ref)

    if prepare is not None and (
        wt_path.exists() or _listed_worktree_state(trunk, wt_path)[0]
        or _branch_exists(trunk, branch)
    ):
        raise GitError("Existing unregistered Epic checkout or branch; preserved for recovery.")
    _remove_stale_worktree(trunk, wt_path)

    if _branch_exists(trunk, branch):
        _git(trunk, "worktree", "add", str(wt_path), branch)
    else:
        _git(trunk, "worktree", "add", "-b", branch, str(wt_path), base_ref)

    if prepare is not None:
        prepare(wt_path)

    record = IntegrationWorktree(
        kind=kind,
        work_id=work_id,
        branch=branch,
        path=wt_path.resolve(),
        base_sha=base_sha,
    )
    if source_room_root is not None:
        from cascade.war_room.chat_store import move_transcript_room

        move_transcript_room(
            work_id,
            source_root=source_room_root,
            destination_root=wt_path,
            root=trunk,
            switch_owner=lambda: _upsert_registry_entry(trunk, record),
        )
    else:
        _upsert_registry_entry(trunk, record)
    return record


def resume_unstarted_epic_worktree(
    entry: IntegrationWorktree,
    *,
    trunk: Path,
    base_sha: str,
    prepare: Callable[[Path], None] | None = None,
) -> IntegrationWorktree | None:
    """Reuse only a clean, canonical checkout with no work beyond the approved base.

    The caller must first prove the Epic is still backlog with no execution
    evidence and recheck its admission gates. Never reset or delete an existing
    branch, and do not treat divergent work as an abandoned provisioning attempt.
    """
    from cascade.board.gitutil import _run as git_run

    if (
        entry.kind != "epic"
        or entry.branch != integration_branch("epic", entry.work_id)
        or entry.path != integration_worktree_path("epic", entry.work_id, trunk=trunk)
        or not entry.path.is_dir()
    ):
        return None
    present, locked = _listed_worktree_state(trunk, entry.path)
    if not present or locked:
        return None
    branch = git_run(["symbolic-ref", "--quiet", "--short", "HEAD"], entry.path, check=False)
    dirty = git_run(["status", "--porcelain", "--untracked-files=all"], entry.path, check=False)
    tip = head_sha(entry.path)
    if (
        branch.returncode or branch.stdout.strip() != entry.branch
        or dirty.returncode or dirty.stdout or not tip
    ):
        return None
    if any(
        _git(trunk, "merge-base", "--is-ancestor", left, right, check=False).returncode
        for left, right in ((entry.base_sha, tip), (tip, base_sha))
    ):
        return None
    # A fast-forward preserves the existing checkout and every commit. The
    # approved revision, not the interrupted attempt's old base, owns new work.
    git_run(["merge", "--ff-only", base_sha], entry.path)
    if prepare is not None:
        prepare(entry.path)
    updated = replace(entry, base_sha=base_sha)
    _upsert_registry_entry(trunk, updated)
    return updated


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


def _boards_for_trunk(trunk: Path, *, readonly: bool = False) -> list[BoardIndex]:
    """One board scan per checkout. Callers must not scan again per work id."""

    trunk = trunk.resolve()
    boards = [list_board(trunk)]
    entries = load_registry_readonly(trunk) if readonly else load_registry(trunk)
    for entry in entries:
        if entry.path.is_dir():
            boards.append(list_board(entry.path))
    return boards


def invalidate_merged_board(trunk: Path) -> None:
    """Drop the shared supervisor-board snapshot after a board or registry write."""

    roots = {locate_trunk(trunk).resolve()}
    from cascade.board.context import get_project_context

    project = get_project_context()
    if project is not None:
        roots.update(
            {
                project.target.root.resolve(),
                project.tracking.root.resolve(),
            }
        )
    with _merged_board_cache_lock:
        for root in roots:
            _merged_board_cache.pop(root, None)


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


def refresh_merged_board(trunk: Path) -> BoardIndex:
    """Read a new supervisor board snapshot for an authorization boundary.

    Unlike :func:`merged_board`, this deliberately ignores both the short-lived
    cache and a request-scoped ``merged_board_snapshot``.  Those snapshots are
    useful for coherent read responses, but are never authorization evidence.
    """

    trunk = locate_trunk(trunk).resolve()
    with _merged_board_cache_lock:
        board = _merged_board_uncached(trunk)
        _merged_board_cache[trunk] = (time.monotonic() + _MERGED_BOARD_CACHE_TTL_S, board)
        return board


def merged_board_readonly(trunk: Path) -> BoardIndex:
    """Read a fresh merged board without creating registry lock state."""

    return _merged_board_uncached(locate_trunk(trunk).resolve(), readonly=True)


@contextmanager
def merged_board_snapshot(trunk: Path, board: BoardIndex) -> Iterator[None]:
    """Reuse one board view during a read-only response on this context."""

    token = _board_snapshot.set((locate_trunk(trunk).resolve(), board))
    try:
        yield
    finally:
        _board_snapshot.reset(token)


def _merged_board_uncached(trunk: Path, *, readonly: bool = False) -> BoardIndex:
    """Build the supervisor view from trunk and registered worktrees."""

    trunk = trunk.resolve()
    boards = _boards_for_trunk(trunk, readonly=readonly)
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
    from cascade.epic.return_graph import project_returns

    project_returns(trunk, BoardIndex(by_id=by_id))
    from cascade.workspace.backlog_snapshot import read_provenance, snapshot_board

    if read_provenance(trunk) is not None:
        for work_id, meta in snapshot_board(trunk).by_id.items():
            if meta.tier != "epic":
                continue
            current = by_id.get(work_id)
            if meta.status == "cancelled" and meta.path.parent.name == "3_completed":
                if current is None or (
                    current.tier == "epic"
                    and current.status == "backlog"
                    and current.path.parent.name == "1_backlog"
                ):
                    # A merged cancellation supersedes a stale local backlog copy.
                    by_id[work_id] = meta
                continue
            if meta.path.parent.name != "1_backlog":
                continue
            if current is None or (
                current.tier == "epic"
                and current.status == "backlog"
                and current.path.parent.name == "1_backlog"
            ):
                # The approved snapshot supersedes only a stale backlog copy.
                # Active/completed rows and integration worktrees stay live.
                by_id[work_id] = meta
    return BoardIndex(by_id=by_id)


def resolve_mutation_owner(
    work_id: str,
    *,
    trunk: Path,
    tier: str | None = None,
    parent: str | None = None,
) -> Path:
    """Prove the one checkout authorized to mutate ``work_id``.

    The merged board is intentionally not authority here.  Ownership follows
    the canonical tracking repository, exact registry identity, expected
    branch, and parent lineage.  Historical copies in sibling worktrees remain
    useful to read but cannot win a lifecycle write by column rank.
    """

    from cascade.board.context import get_project_context, resolve_tracking_root
    from cascade.workspace.backlog_snapshot import snapshot_board

    requested = Path(trunk).resolve()
    tracking = locate_trunk(resolve_tracking_root(requested)).resolve()
    project = get_project_context()
    product = tracking
    if project is not None:
        product = locate_trunk(project.target.root).resolve()
        tracking = locate_trunk(project.tracking.root).resolve()
        allowed = (
            requested in {product, tracking}
            or requested.is_relative_to(product / ".cascade" / "worktrees")
            or requested.is_relative_to(tracking / ".cascade")
        )
        if not allowed:
            raise MutationOwnerError(
                work_id,
                "the requested repository has no canonical product/tracking role",
                f"retry with product root {product} or tracking root {tracking}",
            )

    registry = load_registry(product)
    boards: dict[Path, BoardIndex] = {tracking: list_board(tracking)}
    for entry in registry:
        if entry.path.is_dir():
            boards.setdefault(entry.path.resolve(), list_board(entry.path))

    # Returned work is an admitted reconstruction path.  Discover it directly;
    # the merged-board winner is a read projection and is never consulted for
    # mutation authority.
    returned_roots: list[Path] = []
    returns_home = tracking / ".cascade" / "epic-returns"
    if returns_home.is_dir():
        for manifest in sorted(returns_home.glob("*/manifest.json")):
            try:
                return_state = json.loads(
                    manifest.read_text(encoding="utf-8")
                ).get("state")
            except (OSError, json.JSONDecodeError, AttributeError) as exc:
                raise MutationOwnerError(
                    work_id,
                    f"return manifest is unreadable: {manifest}",
                    "repair or remove the corrupt return manifest through lifecycle recovery",
                ) from exc
            if return_state not in {"returning", "returned"}:
                continue
            candidate = manifest.parent.resolve()
            if work_id in list_board(candidate).by_id:
                returned_roots.append(candidate)
    if len(returned_roots) > 1:
        raise MutationOwnerError(
            work_id,
            "multiple returned lifecycle snapshots claim mutation ownership",
            "reconcile the return manifests before retrying",
        )
    returned_root = returned_roots[0] if returned_roots else None
    snapshot_copy = snapshot_board(product).by_id.get(work_id)

    copies = [board.by_id[work_id] for board in boards.values() if work_id in board.by_id]
    if returned_root is not None:
        returned_board = list_board(returned_root)
        if work_id in returned_board.by_id:
            copies.append(returned_board.by_id[work_id])
    if not copies:
        if snapshot_copy is not None:
            raise MutationOwnerError(
                work_id,
                "the only canonical provenance is a read-only backlog snapshot",
                "activate or import the backlog item before mutating it",
            )
        raise MutationOwnerError(
            work_id,
            "no document copy has canonical product/tracking provenance",
            "restore the work document in its registered owner or reconstruct it through the lifecycle recovery path",
        )
    if (
        snapshot_copy is not None
        and returned_root is None
        and not any(row.work_id == work_id for row in registry)
        and all(copy.status == "backlog" for copy in copies)
    ):
        raise MutationOwnerError(
            work_id,
            "canonical provenance is a read-only backlog snapshot",
            "activate or import the backlog item before mutating it",
        )

    tiers = {copy.tier for copy in copies}
    parents = {copy.parent for copy in copies}
    if tier is not None:
        tiers.add(tier)
    if parent is not None:
        parents.add(parent)
    if len(tiers) != 1 or len(parents) != 1:
        raise MutationOwnerError(
            work_id,
            "document copies disagree on tier or parent lineage",
            "reconcile the conflicting copies and registry before retrying",
        )
    resolved_tier = next(iter(tiers))
    resolved_parent = next(iter(parents))

    if returned_root is not None:
        owner = returned_root.resolve()
    elif resolved_tier == "epic":
        entry = _exact_owner_entry(registry, "epic", work_id, product)
        owner = entry.path.resolve() if entry is not None and product == tracking else tracking
    elif resolved_tier == "feature":
        entry = _exact_owner_entry(registry, "feature", work_id, product)
        if entry is not None:
            owner = tracking if product != tracking else entry.path.resolve()
        else:
            if not resolved_parent:
                raise MutationOwnerError(
                    work_id, "feature has no parent owner", "restore its parent epic metadata"
                )
            owner = resolve_mutation_owner(resolved_parent, trunk=product, tier="epic")
    elif resolved_tier == "task":
        if not resolved_parent:
            raise MutationOwnerError(
                work_id, "task has no parent owner", "restore its parent feature metadata"
            )
        # A Task checkout owns execution rather than its Markdown file, but a
        # present registration is still part of the lifecycle identity and
        # must not silently drift to another path or branch.
        _exact_owner_entry(registry, "task", work_id, product)
        owner = resolve_mutation_owner(resolved_parent, trunk=product, tier="feature")
    else:
        raise MutationOwnerError(
            work_id, f"unsupported tier {resolved_tier!r}", "repair the work document tier"
        )

    owner_board = list_board(owner)
    owned = owner_board.by_id.get(work_id)
    if owned is None or owned.tier != resolved_tier or owned.parent != resolved_parent:
        raise MutationOwnerError(
            work_id,
            f"registered owner {owner} does not contain the expected document",
            "restore the document in that checkout or repair the exact registry identity",
        )
    return owner


def _exact_owner_entry(
    registry: list[IntegrationWorktree],
    kind: IntegrationKind,
    work_id: str,
    trunk: Path,
) -> IntegrationWorktree | None:
    matches = [row for row in registry if row.kind == kind and row.work_id == work_id]
    if len(matches) > 1:
        raise MutationOwnerError(
            work_id,
            "multiple registry entries claim the same owner identity",
            "remove the duplicate registry entry after verifying the live checkout",
        )
    if not matches:
        return None
    entry = matches[0]
    expected_branch = integration_branch(kind, work_id)
    expected_path = integration_worktree_path(kind, work_id, trunk=trunk)
    if entry.branch != expected_branch or entry.path.resolve() != expected_path:
        raise MutationOwnerError(
            work_id,
            "registered branch or checkout path conflicts with canonical ownership",
            f"repair the registry to {expected_branch} at {expected_path}",
        )
    if not entry.path.is_dir():
        raise MutationOwnerError(
            work_id,
            "the registered owner checkout is missing",
            "repair the registered worktree before retrying the mutation",
        )
    branch = _git(entry.path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch.returncode != 0 or branch.stdout.strip() != expected_branch:
        raise MutationOwnerError(
            work_id,
            "the registered checkout is on a different or detached branch",
            f"restore checkout {entry.path} to {expected_branch}",
        )
    return entry


def doc_filesystem_root(work_id: str, *, trunk: Path) -> Path:
    """Return the exact checkout authorized to mutate ``work_id``."""

    return resolve_mutation_owner(work_id, trunk=trunk)


def projected_doc_filesystem_root(work_id: str, *, trunk: Path) -> Path:
    """Return the checkout containing the merged-board read projection."""

    meta = _best_meta_for_id(work_id, trunk=trunk)
    path = meta.path.resolve()
    from cascade.epic.return_graph import returned_root_for_path

    returned = returned_root_for_path(trunk, path)
    if returned is not None:
        return returned
    from cascade.workspace.backlog_snapshot import snapshot_root

    snap = snapshot_root(trunk).resolve()
    if path.is_relative_to(snap):
        return snap
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
