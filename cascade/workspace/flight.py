"""Supervisor flight report: in-flight paths and overlap detection (task_068)."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import time

from cascade.board.context import resolve_root
from cascade.board.types import BoardIndex
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import (
    IntegrationWorktree,
    branch_exists,
    integration_branch,
    load_registry,
    merged_board,
)
from cascade.workspace.integration_worktree import _git as integration_git
from cascade.workspace.types import FlightOverlap, FlightReport

_TOAST_KIND = "flight_overlap"

OverlapSignature = tuple[tuple[str, ...], tuple[str, ...]]

_last_overlap_signatures: set[OverlapSignature] = set()
_toasted_overlap_signatures: set[OverlapSignature] = set()
_cached_report: FlightReport | None = None
_cached_root: Path | None = None
_cached_at: float | None = None

# Flight information is advisory UI data. Rebuilding it on every 500ms
# watchdog tick reparses every registered worktree and can starve the War Room.
DEFAULT_REFRESH_TTL_SECONDS = 10.0


def clear_flight_memory() -> None:
    """Reset overlap toast state and cache (tests only)."""

    global _cached_report, _cached_root, _cached_at
    _last_overlap_signatures.clear()
    _toasted_overlap_signatures.clear()
    _cached_report = None
    _cached_root = None
    _cached_at = None


def get_cached_flight_report(*, root: Path | None = None) -> FlightReport:
    """Return the last report refreshed for ``root``, or compute once if missing."""

    repo = resolve_root(root)
    if _cached_report is not None and _cached_root == repo.resolve():
        return _cached_report
    return flight_report(repo)


def flight_report(root: Path | None = None) -> FlightReport:
    """Deterministic in-flight picture with path diffs and overlap intersections."""

    repo = resolve_root(root).resolve()
    board = merged_board(repo)
    epics: list[IntegrationWorktree] = []
    features: list[IntegrationWorktree] = []
    tasks: list[IntegrationWorktree] = []
    changed_paths: dict[str, tuple[str, ...]] = {}

    for entry in sorted(load_registry(repo), key=lambda e: (e.kind, e.work_id)):
        if not _is_in_flight(repo, entry, board):
            continue
        paths = _changed_paths(repo, entry)
        changed_paths[entry.work_id] = paths
        if entry.kind == "epic":
            epics.append(entry)
        elif entry.kind == "feature":
            features.append(entry)
        else:
            tasks.append(entry)

    overlaps = _compute_overlaps(repo, features, changed_paths, board)
    report = FlightReport(
        epics=tuple(epics),
        features=tuple(features),
        tasks=tuple(tasks),
        changed_paths=changed_paths,
        overlaps=overlaps,
    )
    global _cached_report, _cached_root, _cached_at
    _cached_report = report
    _cached_root = repo
    _cached_at = time.monotonic()
    return report


def refresh_flight_report(root: Path | None = None) -> FlightReport:
    """Recompute the report and enqueue overlap toasts for newly seen intersections."""

    repo = resolve_root(root)
    report = flight_report(repo)
    _maybe_enqueue_overlap_toasts(repo, report)
    return report


def refresh_flight_report_if_stale(
    root: Path | None = None,
    *,
    max_age_seconds: float = DEFAULT_REFRESH_TTL_SECONDS,
) -> FlightReport:
    """Refresh advisory flight data at most once per ``max_age_seconds``.

    Explicit callers of :func:`refresh_flight_report` still force an immediate
    rebuild. The watchdog uses this throttled path because its health loop runs
    much more frequently than the UI needs a new overlap snapshot.
    """

    repo = resolve_root(root).resolve()
    now = time.monotonic()
    if (
        _cached_report is not None
        and _cached_root == repo
        and _cached_at is not None
        and now - _cached_at < max(0.0, max_age_seconds)
    ):
        return _cached_report
    return refresh_flight_report(repo)


def _tier_for_kind(kind: str) -> str:
    return {"epic": "epic", "feature": "feature", "task": "task"}[kind]


def _is_in_flight(trunk: Path, entry: IntegrationWorktree, board: BoardIndex) -> bool:
    if not branch_exists(trunk, entry.branch):
        return False
    meta = board.by_id.get(entry.work_id)
    if meta is None:
        return False
    if meta.tier != _tier_for_kind(entry.kind):
        return False
    return meta.path.parent.name == "2_active"


def _changed_paths(trunk: Path, entry: IntegrationWorktree) -> tuple[str, ...]:
    tip = _resolve_branch_tip(trunk, entry.branch)
    if tip is None:
        return ()
    return _diff_name_only(trunk, entry.base_sha, tip)


def _resolve_branch_tip(trunk: Path, branch: str) -> str | None:
    result = integration_git(trunk, "rev-parse", branch, check=False)
    if result.returncode != 0:
        return None
    sha = (result.stdout or "").strip()
    return sha or None


def _diff_name_only(trunk: Path, base_sha: str, tip_sha: str) -> tuple[str, ...]:
    if base_sha == tip_sha:
        return ()
    result = integration_git(
        trunk,
        "diff",
        "--name-only",
        f"{base_sha}..{tip_sha}",
        check=False,
    )
    if result.returncode != 0:
        return ()
    paths = sorted({line.strip() for line in (result.stdout or "").splitlines() if line.strip()})
    return tuple(paths)


def _epic_delta_paths(trunk: Path, epic_id: str, since_sha: str) -> tuple[str, ...]:
    branch = integration_branch("epic", epic_id)
    tip = _resolve_branch_tip(trunk, branch)
    if tip is None:
        return ()
    return _diff_name_only(trunk, since_sha, tip)


def _compute_overlaps(
    trunk: Path,
    features: list[IntegrationWorktree],
    changed_paths: dict[str, tuple[str, ...]],
    board: BoardIndex,
) -> tuple[FlightOverlap, ...]:
    records: list[FlightOverlap] = []

    for left, right in combinations(sorted(features, key=lambda e: e.work_id), 2):
        shared = _intersect_paths(changed_paths.get(left.work_id, ()), changed_paths.get(right.work_id, ()))
        if not shared:
            continue
        work_ids = tuple(sorted((left.work_id, right.work_id)))
        records.append(FlightOverlap(paths=shared, work_ids=work_ids))

    for feat in sorted(features, key=lambda e: e.work_id):
        meta = board.by_id.get(feat.work_id)
        epic_id = meta.parent if meta is not None else None
        if not epic_id:
            continue
        epic_paths = _epic_delta_paths(trunk, epic_id, feat.base_sha)
        if not epic_paths:
            continue
        shared = _intersect_paths(changed_paths.get(feat.work_id, ()), epic_paths)
        if not shared:
            continue
        work_ids = tuple(sorted((feat.work_id, epic_id)))
        records.append(FlightOverlap(paths=shared, work_ids=work_ids))

    return tuple(sorted(records, key=_overlap_sort_key))


def _intersect_paths(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    if not a or not b:
        return ()
    shared = sorted(set(a) & set(b))
    return tuple(shared)


def _overlap_sort_key(record: FlightOverlap) -> tuple[str, ...]:
    return record.work_ids + record.paths


def _overlap_signature(record: FlightOverlap) -> OverlapSignature:
    return (record.work_ids, record.paths)


def _maybe_enqueue_overlap_toasts(root: Path, report: FlightReport) -> None:
    current = {_overlap_signature(o) for o in report.overlaps}
    new_sigs = current - _last_overlap_signatures
    for sig in sorted(new_sigs):
        if sig in _toasted_overlap_signatures:
            continue
        record = next(r for r in report.overlaps if _overlap_signature(r) == sig)
        _append_overlap_toast(root, record, merged_board(root))
        _toasted_overlap_signatures.add(sig)
    _last_overlap_signatures.clear()
    _last_overlap_signatures.update(current)


def _append_overlap_toast(root: Path, record: FlightOverlap, board: BoardIndex) -> None:
    paths_text = ", ".join(record.paths)
    ids_text = " vs ".join(record.work_ids)
    message = f"Path overlap ({ids_text}): {paths_text}"
    epic_id = _epic_id_from_overlap(record.work_ids, board)
    payload: dict[str, object] = {
        "kind": _TOAST_KIND,
        "message": message,
        "body": message,
        "work_ids": list(record.work_ids),
        "paths": list(record.paths),
    }
    if epic_id:
        payload["epic_id"] = epic_id
        payload["id"] = epic_id
    try:
        append_event(
            "war_room",
            Event(
                type="Toast",
                ts=datetime.now(timezone.utc),
                payload=payload,
                dest="war_room",
            ),
            root=root,
        )
    except OSError:
        return


def _epic_id_from_overlap(work_ids: tuple[str, ...], board: BoardIndex) -> str | None:
    for work_id in work_ids:
        if work_id.startswith("epic_"):
            return work_id
    for work_id in work_ids:
        if not work_id.startswith("feat_"):
            continue
        meta = board.by_id.get(work_id)
        if meta is not None and meta.parent:
            return meta.parent
    return None
