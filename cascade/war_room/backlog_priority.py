"""Durable, per-Epic ordering for backlog features.

The priority file is workspace state rather than plan state: every integration
worktree resolves it through the trunk, so all War Room clients observe the
same order without creating plan commits.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from cascade.board.context import resolve_root
from cascade.board.types import BoardIndex, WorkMeta
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import (
    invalidate_merged_board,
    locate_trunk,
    merged_board,
)

_SCHEMA_VERSION = 1
_STATE_NAME = "backlog_feature_priority.json"
_LOCK_NAME = "backlog_feature_priority.lock"
_BACKLOG_STATUSES = frozenset({"backlog", "ready_to_plan"})


@dataclass(frozen=True)
class BacklogPriority:
    """The canonical backlog-feature order and its optimistic-write token."""

    epic_id: str
    feature_ids: tuple[str, ...]
    version: int

    @property
    def token(self) -> str:
        """Return the opaque HTTP concurrency token for this exact projection."""

        material = json.dumps(
            [_SCHEMA_VERSION, self.version, self.epic_id, self.feature_ids],
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


class BacklogPriorityError(ValueError):
    """A guarded reorder was refused without applying the submitted order."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        current: BacklogPriority | None = None,
    ) -> None:
        self.code = code
        self.current = current
        super().__init__(message)


class BacklogPriorityStorageError(RuntimeError):
    """The durable priority file cannot be safely read."""


def read_backlog_priority(epic_id: str, *, root: Path) -> BacklogPriority:
    """Return canonical current peers, reconciling lifecycle changes durably.

    Existing ranked peers retain their relative order. Newly observed backlog
    features are appended in ID order, while departed peers are compacted out.
    Any membership change advances the version, making older client snapshots
    stale even if they happen to know the new membership.
    """

    trunk = locate_trunk(resolve_root(root))
    with process_lock:
        with _locked_state(trunk):
            board = _fresh_board(trunk)
            _require_epic(epic_id, board)
            state = _load_state(trunk)
            return _reconcile(epic_id, board=board, state=state, trunk=trunk)


def read_backlog_priorities(
    board: BoardIndex,
    *,
    root: Path,
) -> dict[str, BacklogPriority]:
    """Project all current backlog priorities from an already merged board scan."""

    trunk = locate_trunk(resolve_root(root))
    epic_ids = sorted(
        {
            meta.parent
            for meta in board.by_id.values()
            if meta.parent is not None and _is_backlog_peer(meta, meta.parent)
        }
    )
    with process_lock:
        with _locked_state(trunk):
            state = _load_state(trunk)
            before = json.dumps(state, sort_keys=True)
            priorities = {
                epic_id: _reconcile(
                    epic_id,
                    board=board,
                    state=state,
                    trunk=trunk,
                    persist=False,
                )
                for epic_id in epic_ids
            }
            if json.dumps(state, sort_keys=True) != before:
                _save_state(trunk, state)
            return priorities


def reorder_backlog_features(
    epic_id: str,
    feature_ids: Sequence[str],
    *,
    root: Path,
    version: int | None = None,
    expected_token: str | None = None,
) -> BacklogPriority:
    """Atomically replace one Epic's order when token and membership are current."""

    trunk = locate_trunk(resolve_root(root))
    with process_lock:
        with _locked_state(trunk):
            board = _fresh_board(trunk)
            _require_epic(epic_id, board)
            state = _load_state(trunk)
            # Reconcile in memory first. A rejected command must not alter the
            # durable state, even when lifecycle membership changed meanwhile.
            current = _reconcile(
                epic_id,
                board=board,
                state=state,
                trunk=trunk,
                persist=False,
            )

            if expected_token is not None and expected_token != current.token:
                raise BacklogPriorityError(
                    f"stale backlog priority token for {epic_id}",
                    code="stale_priority",
                    current=current,
                )
            if expected_token is None and (
                not isinstance(version, int)
                or isinstance(version, bool)
                or version != current.version
            ):
                raise BacklogPriorityError(
                    f"stale backlog priority version for {epic_id}: "
                    f"expected {current.version}, got {version!r}",
                    code="stale_version",
                    current=current,
                )

            submitted = _validate_submitted_order(
                epic_id,
                feature_ids,
                board=board,
                current=current,
            )
            next_priority = BacklogPriority(
                epic_id=epic_id,
                feature_ids=submitted,
                version=current.version + 1,
            )
            _set_record(state, next_priority)
            _save_state(trunk, state)
            return next_priority


def _validate_submitted_order(
    epic_id: str,
    feature_ids: Sequence[str],
    *,
    board: BoardIndex,
    current: BacklogPriority,
) -> tuple[str, ...]:
    if isinstance(feature_ids, (str, bytes)):
        raise BacklogPriorityError("feature_ids must be a sequence of IDs", code="invalid_order")
    submitted = tuple(feature_ids)
    if any(not isinstance(feature_id, str) for feature_id in submitted):
        raise BacklogPriorityError("feature_ids must contain only strings", code="invalid_order")
    if len(set(submitted)) != len(submitted):
        raise BacklogPriorityError("backlog priority contains duplicate feature IDs", code="duplicate_id")

    for feature_id in submitted:
        meta = board.by_id.get(feature_id)
        if meta is None or meta.tier != "feature":
            raise BacklogPriorityError(
                f"unknown feature ID in backlog priority: {feature_id}",
                code="unknown_id",
            )
        if meta.parent != epic_id:
            raise BacklogPriorityError(
                f"feature {feature_id} does not belong to {epic_id}",
                code="cross_epic_id",
            )
        if not _is_backlog_peer(meta, epic_id):
            raise BacklogPriorityError(
                f"feature {feature_id} is not a current backlog member",
                code="non_backlog_id",
            )

    if set(submitted) != set(current.feature_ids):
        missing = sorted(set(current.feature_ids) - set(submitted))
        raise BacklogPriorityError(
            f"submitted order does not contain exactly the current backlog peers; missing={missing}",
            code="membership_mismatch",
        )
    return submitted


def _require_epic(epic_id: str, board: BoardIndex) -> None:
    meta = board.by_id.get(epic_id)
    if meta is None or meta.tier != "epic":
        raise BacklogPriorityError(f"unknown Epic: {epic_id}", code="unknown_epic")


def _fresh_board(trunk: Path) -> BoardIndex:
    """Bypass the polling cache at the guarded command/read boundary."""

    invalidate_merged_board(trunk)
    return merged_board(trunk)


def _current_peer_ids(epic_id: str, board: BoardIndex) -> tuple[str, ...]:
    return tuple(
        sorted(
            meta.id
            for meta in board.by_id.values()
            if _is_backlog_peer(meta, epic_id)
        )
    )


def _is_backlog_peer(meta: WorkMeta, epic_id: str) -> bool:
    return (
        meta.tier == "feature"
        and meta.parent == epic_id
        and meta.status in _BACKLOG_STATUSES
        and meta.path.parent.name == "1_backlog"
    )


def _reconcile(
    epic_id: str,
    *,
    board: BoardIndex,
    state: dict[str, object],
    trunk: Path,
    persist: bool = True,
) -> BacklogPriority:
    peers = _current_peer_ids(epic_id, board)
    record = _record(state, epic_id)
    if record is None:
        priority = BacklogPriority(epic_id=epic_id, feature_ids=peers, version=1)
        _set_record(state, priority)
        if persist:
            _save_state(trunk, state)
        return priority

    stored_ids, stored_version = record
    peer_set = set(peers)
    reconciled = tuple(feature_id for feature_id in stored_ids if feature_id in peer_set)
    ranked_set = set(reconciled)
    reconciled += tuple(feature_id for feature_id in peers if feature_id not in ranked_set)
    if reconciled != stored_ids:
        priority = BacklogPriority(
            epic_id=epic_id,
            feature_ids=reconciled,
            version=stored_version + 1,
        )
        _set_record(state, priority)
        if persist:
            _save_state(trunk, state)
        return priority
    return BacklogPriority(epic_id=epic_id, feature_ids=stored_ids, version=stored_version)


def _state_path(trunk: Path) -> Path:
    return trunk / ".cascade" / _STATE_NAME


@contextmanager
def _locked_state(trunk: Path) -> Iterator[None]:
    lock_path = trunk / ".cascade" / _LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _empty_state() -> dict[str, object]:
    return {"schema_version": _SCHEMA_VERSION, "epics": {}}


def _load_state(trunk: Path) -> dict[str, object]:
    path = _state_path(trunk)
    if not path.is_file():
        return _empty_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacklogPriorityStorageError(f"cannot read {path}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != _SCHEMA_VERSION:
        raise BacklogPriorityStorageError(f"unsupported backlog priority state at {path}")
    epics = raw.get("epics")
    if not isinstance(epics, dict):
        raise BacklogPriorityStorageError(f"invalid backlog priority state at {path}")
    # Validate every record before a later write could preserve or overwrite it.
    for epic_id in epics:
        if not isinstance(epic_id, str) or _record(raw, epic_id) is None:
            raise BacklogPriorityStorageError(f"invalid backlog priority record at {path}")
    return raw


def _record(state: dict[str, object], epic_id: str) -> tuple[tuple[str, ...], int] | None:
    epics = state.get("epics")
    if not isinstance(epics, dict) or epic_id not in epics:
        return None
    value = epics[epic_id]
    if not isinstance(value, dict):
        return None
    feature_ids = value.get("feature_ids")
    version = value.get("version")
    if (
        not isinstance(feature_ids, list)
        or any(not isinstance(item, str) for item in feature_ids)
        or len(set(feature_ids)) != len(feature_ids)
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        return None
    return tuple(feature_ids), version


def _set_record(state: dict[str, object], priority: BacklogPriority) -> None:
    epics = state.setdefault("epics", {})
    assert isinstance(epics, dict)
    epics[priority.epic_id] = {
        "feature_ids": list(priority.feature_ids),
        "version": priority.version,
    }


def _save_state(trunk: Path, state: dict[str, object]) -> None:
    path = _state_path(trunk)
    path.parent.mkdir(parents=True, exist_ok=True)
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
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
