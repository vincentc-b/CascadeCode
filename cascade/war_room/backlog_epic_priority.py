"""Durable ordering for the visible backlog Epic cards."""

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
from cascade.board.types import BoardIndex
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import (
    invalidate_merged_board,
    locate_trunk,
    merged_board,
)

_STATE_NAME = "backlog_epic_priority.json"
_LOCK_NAME = "backlog_epic_priority.lock"
_SCHEMA_VERSION = 1
_BACKLOG_STATUSES = frozenset({"backlog", "ready_to_plan"})


@dataclass(frozen=True)
class BacklogEpicPriority:
    epic_ids: tuple[str, ...]
    version: int

    @property
    def token(self) -> str:
        material = json.dumps(
            [_SCHEMA_VERSION, self.version, self.epic_ids], separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


class BacklogEpicPriorityError(ValueError):
    def __init__(
        self, message: str, *, code: str, current: BacklogEpicPriority | None = None
    ) -> None:
        self.code = code
        self.current = current
        super().__init__(message)


class BacklogEpicPriorityStorageError(RuntimeError):
    pass


def read_backlog_epic_priority(board: BoardIndex, *, root: Path) -> BacklogEpicPriority:
    """Read the order from the same merged board snapshot used by the board API."""

    trunk = locate_trunk(resolve_root(root))
    with process_lock:
        with _locked_state(trunk):
            state = _load_state(trunk)
            priority = _reconcile(state, board)
            if state != priority:
                _save_state(trunk, priority)
            return priority


def reorder_backlog_epics(
    epic_ids: Sequence[str], *, expected_token: str, root: Path
) -> BacklogEpicPriority:
    """Atomically accept a complete current order, guarded by its token."""

    trunk = locate_trunk(resolve_root(root))
    with process_lock:
        with _locked_state(trunk):
            invalidate_merged_board(trunk)
            board = merged_board(trunk)
            current = _reconcile(_load_state(trunk), board)
            if expected_token != current.token:
                raise BacklogEpicPriorityError(
                    "Backlog epic order changed elsewhere", code="stale_priority", current=current
                )
            submitted = _validate_order(epic_ids, board, current)
            accepted = BacklogEpicPriority(submitted, current.version + 1)
            _save_state(trunk, accepted)
            return accepted


def _current_ids(board: BoardIndex) -> tuple[str, ...]:
    return tuple(
        sorted(
            meta.id
            for meta in board.by_id.values()
            if meta.tier == "epic"
            and meta.status in _BACKLOG_STATUSES
            and meta.path.parent.name == "1_backlog"
        )
    )


def _reconcile(
    stored: BacklogEpicPriority | None, board: BoardIndex
) -> BacklogEpicPriority:
    peers = _current_ids(board)
    if stored is None:
        return BacklogEpicPriority(peers, 1)
    peer_set = set(peers)
    retained = tuple(epic_id for epic_id in stored.epic_ids if epic_id in peer_set)
    ranked_set = set(retained)
    reconciled = retained + tuple(epic_id for epic_id in peers if epic_id not in ranked_set)
    if reconciled == stored.epic_ids:
        return stored
    return BacklogEpicPriority(reconciled, stored.version + 1)


def _validate_order(
    epic_ids: Sequence[str], board: BoardIndex, current: BacklogEpicPriority
) -> tuple[str, ...]:
    if isinstance(epic_ids, (str, bytes)):
        raise BacklogEpicPriorityError("epic_ids must be a list", code="invalid_order")
    submitted = tuple(epic_ids)
    if any(not isinstance(epic_id, str) for epic_id in submitted):
        raise BacklogEpicPriorityError("epic_ids must contain IDs", code="invalid_order")
    if len(set(submitted)) != len(submitted):
        raise BacklogEpicPriorityError("duplicate epic ID", code="duplicate_id")
    for epic_id in submitted:
        meta = board.by_id.get(epic_id)
        if meta is None or meta.tier != "epic":
            raise BacklogEpicPriorityError(f"unknown epic {epic_id}", code="unknown_id")
        if meta.status not in _BACKLOG_STATUSES or meta.path.parent.name != "1_backlog":
            raise BacklogEpicPriorityError(
                f"epic {epic_id} is not in backlog", code="non_backlog_id"
            )
    if set(submitted) != set(current.epic_ids):
        raise BacklogEpicPriorityError(
            "epic_ids must contain exactly the current backlog epics",
            code="membership_mismatch",
        )
    return submitted


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


def _load_state(trunk: Path) -> BacklogEpicPriority | None:
    path = _state_path(trunk)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacklogEpicPriorityStorageError(f"cannot read {path}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != _SCHEMA_VERSION:
        raise BacklogEpicPriorityStorageError(f"invalid backlog epic priority at {path}")
    ids = raw.get("epic_ids")
    version = raw.get("version")
    if (
        not isinstance(ids, list)
        or any(not isinstance(value, str) for value in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise BacklogEpicPriorityStorageError(f"invalid backlog epic priority at {path}")
    return BacklogEpicPriority(tuple(ids), version)


def _save_state(trunk: Path, priority: BacklogEpicPriority) -> None:
    path = _state_path(trunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(
                {"schema_version": _SCHEMA_VERSION, "version": priority.version,
                 "epic_ids": list(priority.epic_ids)},
                handle, indent=2, sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
