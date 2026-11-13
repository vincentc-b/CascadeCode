"""Durable workspace-shared attention state for newly observed Features.

The ledger is runtime state, not a planning document.  It lives on the canonical
tracking trunk so all managed worktrees observe the same acknowledgements.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from cascade.board.context import resolve_tracking_root
from cascade.board.errors import BoardError, SchemaError
from cascade.board.types import BoardIndex
from cascade.board.work_ids import parse_work_id_parts
from cascade.workspace.integration_worktree import locate_trunk, merged_board_readonly

SCHEMA_VERSION = 1
LEDGER_NAME = "feature_attention.json"
MARKER_NAME = "feature_attention.initialized"
LOCK_NAME = "feature_attention.lock"

_PROVENANCE = frozenset({"baseline", "FeatureMinted", "discovered"})
_OPEN_FEATURE_STATUSES = frozenset({"backlog", "ready_to_plan"})
_ACTIVE_EPIC_STATUSES = frozenset({"active", "blocked"})
_thread_lock = threading.RLock()


class AttentionUnavailable(RuntimeError):
    """The durable attention ledger cannot safely accept a mutation."""


@dataclass(frozen=True)
class AttentionSnapshot:
    """One validated ledger snapshot, or an explicit unavailable state."""

    state: Literal["available", "unavailable"]
    ledger: dict[str, Any] | None = None
    reason: str | None = None

    @property
    def revision(self) -> int | None:
        if self.ledger is None:
            return None
        return self.ledger["revision"]


@dataclass(frozen=True)
class AttentionPaths:
    ledger: Path
    marker: Path
    lock: Path


def feature_attention_paths(root: Path) -> AttentionPaths:
    """Resolve the single state location shared by split roots and worktrees."""

    trunk = locate_trunk(resolve_tracking_root(Path(root).resolve()))
    state_dir = trunk / ".cascade"
    return AttentionPaths(
        ledger=state_dir / LEDGER_NAME,
        marker=state_dir / MARKER_NAME,
        lock=state_dir / LOCK_NAME,
    )


class AttentionTransaction:
    """Mutation capability valid only while the attention lock is held."""

    def __init__(self, paths: AttentionPaths, snapshot: AttentionSnapshot) -> None:
        self.paths = paths
        self.snapshot = snapshot

    @property
    def available(self) -> bool:
        return self.snapshot.state == "available"

    def record_feature_minted(
        self,
        feature_id: str,
        epic_id: str,
        *,
        observed_at: datetime | None = None,
    ) -> AttentionSnapshot:
        """Record mint provenance once after the Feature has persisted durably."""

        ledger = self._writable_ledger()
        _validate_identity(feature_id, epic_id)
        if feature_id in ledger["features"]:
            return self.snapshot
        ledger["features"][feature_id] = _record(
            epic_id=epic_id,
            provenance="FeatureMinted",
            observed_at=observed_at or _now(),
            attention_eligible=True,
        )
        self.snapshot = self._commit(ledger)
        return self.snapshot

    def _writable_ledger(self) -> dict[str, Any]:
        if self.snapshot.state != "available" or self.snapshot.ledger is None:
            raise AttentionUnavailable(self.snapshot.reason or "attention unavailable")
        # Mutations build a replacement value so a failed write never changes the
        # last validated in-memory snapshot either.
        return json.loads(json.dumps(self.snapshot.ledger))

    def _commit(self, ledger: dict[str, Any]) -> AttentionSnapshot:
        ledger["revision"] += 1
        _validate_ledger(ledger)
        try:
            _atomic_json(self.paths.ledger, ledger)
        except OSError as exc:
            raise AttentionUnavailable(f"attention write failed: {exc}") from exc
        return AttentionSnapshot("available", ledger=ledger)


@contextmanager
def feature_attention_transaction(
    root: Path,
    *,
    board: BoardIndex | None = None,
) -> Iterator[AttentionTransaction]:
    """Bootstrap/reconcile and hold the shared lock for a mint transaction."""

    paths = feature_attention_paths(root)
    with _locked(paths.lock):
        snapshot = _initialize_locked(paths, root=Path(root), board=board)
        yield AttentionTransaction(paths, snapshot)


def initialize_feature_attention(
    root: Path,
    *,
    board: BoardIndex | None = None,
) -> AttentionSnapshot:
    """Run first-rollout bootstrap or startup reconciliation exactly once."""

    paths = feature_attention_paths(root)
    with _locked(paths.lock):
        return _initialize_locked(paths, root=Path(root), board=board)


def read_feature_attention(root: Path) -> AttentionSnapshot:
    """Read without bootstrapping, reconciling, or repairing initialization."""

    paths = feature_attention_paths(root)
    with _locked(paths.lock):
        marker_state = _marker_state(paths.marker)
        if not paths.ledger.exists():
            reason = (
                "ledger_missing_after_initialization"
                if marker_state == "valid"
                else "uninitialized"
            )
            return AttentionSnapshot("unavailable", reason=reason)
        ledger, reason = _load_ledger(paths.ledger)
        if ledger is None:
            return AttentionSnapshot("unavailable", reason=reason)
        if marker_state != "valid":
            return AttentionSnapshot("unavailable", reason="initialization_incomplete")
        return AttentionSnapshot("available", ledger=ledger)


def _initialize_locked(
    paths: AttentionPaths,
    *,
    root: Path,
    board: BoardIndex | None,
) -> AttentionSnapshot:
    marker_state = _marker_state(paths.marker)
    ledger_exists = paths.ledger.exists()

    if not ledger_exists:
        if marker_state != "missing":
            return AttentionSnapshot(
                "unavailable", reason="ledger_missing_after_initialization"
            )
        try:
            canonical_board = board or _canonical_board(root)
        except (BoardError, OSError) as exc:
            return AttentionSnapshot(
                "unavailable", reason=f"baseline_board_unavailable: {exc}"
            )
        observed_at = _now()
        ledger = {
            "schema_version": SCHEMA_VERSION,
            "revision": 1,
            "baseline_at": observed_at.isoformat(),
            "features": _baseline_records(canonical_board, observed_at),
        }
        try:
            _atomic_json(paths.ledger, ledger)
            _write_marker(paths.marker)
        except OSError as exc:
            return AttentionSnapshot("unavailable", reason=f"bootstrap_failed: {exc}")
        return AttentionSnapshot("available", ledger=ledger)

    ledger, reason = _load_ledger(paths.ledger)
    if ledger is None:
        return AttentionSnapshot("unavailable", reason=reason)
    if marker_state == "invalid":
        return AttentionSnapshot("unavailable", reason="invalid_initialization_marker")
    if marker_state == "missing":
        try:
            _write_marker(paths.marker)
        except OSError as exc:
            return AttentionSnapshot(
                "unavailable", reason=f"marker_finalize_failed: {exc}"
            )

    try:
        canonical_board = board or _canonical_board(root)
    except (BoardError, OSError) as exc:
        return AttentionSnapshot(
            "unavailable", reason=f"reconciliation_board_unavailable: {exc}"
        )
    replacement = json.loads(json.dumps(ledger))
    observed_at = _now()
    changed = False
    for feature_id, meta in sorted(canonical_board.by_id.items()):
        if meta.tier != "feature" or feature_id in replacement["features"]:
            continue
        if not _is_valid_identity(feature_id, meta.parent):
            continue
        replacement["features"][feature_id] = _record(
            epic_id=meta.parent,
            provenance="discovered",
            observed_at=observed_at,
            attention_eligible=True,
        )
        changed = True
    if not changed:
        return AttentionSnapshot("available", ledger=ledger)
    replacement["revision"] += 1
    try:
        _validate_ledger(replacement)
        _atomic_json(paths.ledger, replacement)
    except (OSError, ValueError) as exc:
        return AttentionSnapshot("unavailable", reason=f"reconciliation_failed: {exc}")
    return AttentionSnapshot("available", ledger=replacement)


def _canonical_board(root: Path) -> BoardIndex:
    trunk = locate_trunk(resolve_tracking_root(root.resolve()))
    return merged_board_readonly(trunk)


def _baseline_records(board: BoardIndex, observed_at: datetime) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for feature_id, meta in sorted(board.by_id.items()):
        if meta.tier != "feature" or not _is_valid_identity(feature_id, meta.parent):
            continue
        parent = board.by_id.get(meta.parent)
        eligible = (
            meta.status in _OPEN_FEATURE_STATUSES
            and parent is not None
            and parent.tier == "epic"
            and parent.status in _ACTIVE_EPIC_STATUSES
        )
        records[feature_id] = _record(
            epic_id=meta.parent,
            provenance="baseline",
            observed_at=observed_at,
            attention_eligible=eligible,
        )
    return records


def _record(
    *,
    epic_id: str,
    provenance: str,
    observed_at: datetime,
    attention_eligible: bool,
) -> dict[str, Any]:
    return {
        "epic_id": epic_id,
        "provenance": provenance,
        "first_observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "attention_eligible": attention_eligible,
        "seen": None,
    }


def _load_ledger(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _validate_ledger(raw)
    except OSError as exc:
        return None, f"ledger_unreadable: {exc}"
    except (json.JSONDecodeError, ValueError, SchemaError) as exc:
        return None, f"ledger_invalid: {exc}"
    return raw, None


def _validate_ledger(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "revision",
        "baseline_at",
        "features",
    }:
        raise ValueError("invalid ledger fields")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported schema version")
    if type(value["revision"]) is not int or value["revision"] < 1:
        raise ValueError("invalid revision")
    _validate_timestamp(value["baseline_at"], "baseline_at")
    features = value["features"]
    if not isinstance(features, dict):
        raise ValueError("features must be an object")
    for feature_id, record in features.items():
        if not isinstance(feature_id, str) or not isinstance(record, dict):
            raise ValueError("invalid feature record")
        if set(record) != {
            "epic_id",
            "provenance",
            "first_observed_at",
            "attention_eligible",
            "seen",
        }:
            raise ValueError(f"invalid fields for {feature_id}")
        _validate_identity(feature_id, record["epic_id"])
        if record["provenance"] not in _PROVENANCE:
            raise ValueError(f"invalid provenance for {feature_id}")
        _validate_timestamp(record["first_observed_at"], "first_observed_at")
        if type(record["attention_eligible"]) is not bool:
            raise ValueError(f"invalid eligibility for {feature_id}")
        seen = record["seen"]
        if seen is not None:
            if not isinstance(seen, dict) or set(seen) != {"actor", "at"}:
                raise ValueError(f"invalid acknowledgement for {feature_id}")
            if not isinstance(seen["actor"], str) or not seen["actor"].strip():
                raise ValueError(f"invalid acknowledgement actor for {feature_id}")
            _validate_timestamp(seen["at"], "seen.at")


def _validate_identity(feature_id: object, epic_id: object) -> None:
    if not isinstance(feature_id, str) or not isinstance(epic_id, str):
        raise ValueError("feature and epic ids must be strings")
    feature = parse_work_id_parts(feature_id)
    epic = parse_work_id_parts(epic_id)
    if feature.tier != "feature" or epic.tier != "epic":
        raise ValueError("attention record has invalid tier identity")


def _is_valid_identity(feature_id: str, epic_id: str | None) -> bool:
    try:
        _validate_identity(feature_id, epic_id)
    except (SchemaError, ValueError):
        return False
    return True


def _validate_timestamp(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")


def _marker_state(path: Path) -> Literal["missing", "valid", "invalid"]:
    if not path.exists():
        return "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid"
    return "valid" if value == {"schema_version": SCHEMA_VERSION} else "invalid"


def _write_marker(path: Path) -> None:
    _atomic_json(path, {"schema_version": SCHEMA_VERSION})


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _thread_lock:
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "AttentionPaths",
    "AttentionSnapshot",
    "AttentionTransaction",
    "AttentionUnavailable",
    "feature_attention_paths",
    "feature_attention_transaction",
    "initialize_feature_attention",
    "read_feature_attention",
]
