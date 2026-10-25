"""Periodic direct-report observation and bounded supervisor remediation."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_root
from cascade.board.paths import legal_folder
from cascade.board.store import read_doc
from cascade.board.types import WorkDoc
from cascade.feature.recovery import retry_task
from cascade.task.execution import execution_views
from cascade.watchdog.blockage import (
    propagate_direct_report_blockage,
    reconcile_direct_report_blockage,
)
from cascade.watchdog.config import supervisor_health_sweep_seconds
from cascade.watchdog.lock import process_lock
from cascade.workspace.integration_worktree import merged_board

Classification = Literal["no_action", "remediation_eligible", "unresolved"]
_log = logging.getLogger(__name__)
_last_sweep_at: dict[Path, float] = {}


@dataclass(frozen=True)
class ChildHealthObservation:
    supervisor_id: str
    supervisor_status: str
    child_id: str
    child_tier: str
    child_status: str
    child_sha: str | None
    classification: Classification
    reason: str
    execution_attempt: int | None = None
    execution_phase: str | None = None
    execution_outcome: str | None = None


@dataclass(frozen=True)
class RemediationIncidentKey:
    supervisor_id: str
    child_id: str
    observed_child_sha: str

    @property
    def storage_key(self) -> str:
        return "\0".join((self.supervisor_id, self.child_id, self.observed_child_sha))


def classify_child(
    supervisor: WorkDoc,
    child: WorkDoc,
    execution: dict[str, Any] | None = None,
) -> ChildHealthObservation:
    """Classify one canonical direct report without mutating lifecycle state."""

    status = child.meta.status
    health = execution.get("health") if execution else None
    classification: Classification = "no_action"
    reason = "healthy_or_not_actionable"
    if status in {"completed", "cancelled"}:
        reason = "terminal_child"
    elif status == "cancelling":
        reason = "cancellation_in_progress"
    elif status in {"backlog", "ready_to_plan"}:
        reason = "normal_dispatch_authority"
    elif status == "active" and child.meta.tier == "task" and health == "merge_blocked":
        classification, reason = "unresolved", "merge_blocked"
    elif status == "active" and child.meta.tier == "task" and health == "stale":
        reason = "delegated_to_task_watchdog"
    elif status == "blocked" and child.meta.tier == "task":
        if health == "failed":
            classification, reason = "remediation_eligible", "blocked_task_failed"
        else:
            classification, reason = "unresolved", "blocked_task_without_terminal_failure"
    elif status == "blocked" and child.meta.tier == "feature":
        classification, reason = "unresolved", "blocked_feature_has_no_safe_retry"
    elif status != "active":
        classification, reason = "unresolved", "unrecognized_snapshot"
    return ChildHealthObservation(
        supervisor_id=supervisor.meta.id,
        supervisor_status=supervisor.meta.status,
        child_id=child.meta.id,
        child_tier=child.meta.tier,
        child_status=status,
        child_sha=child.sha,
        classification=classification,
        reason=reason,
        execution_attempt=_optional_int(execution, "attempt"),
        execution_phase=_optional_str(execution, "phase"),
        execution_outcome=_optional_str(execution, "outcome"),
    )


def sweep_supervisor_health(root: Path | None = None) -> list[ChildHealthObservation]:
    """Inspect direct reports, reconciling derived supervisor blockage."""

    repo = resolve_root(root)
    observations: list[ChildHealthObservation] = []
    with process_lock:
        board = merged_board(repo)
        supervisors = [
            meta
            for meta in board.by_id.values()
            if meta.tier in {"epic", "feature"}
            and (
                meta.status == "active"
                or (meta.status == "blocked" and meta.monitoring_blockers)
            )
        ]
        task_ids = {
            child_id
            for supervisor in supervisors
            for child_id in supervisor.children
            if (child := board.by_id.get(child_id)) is not None and child.tier == "task"
        }
        views = execution_views(task_ids, root=repo)
        for supervisor_meta in supervisors:
            try:
                supervisor = read_doc(supervisor_meta.id, root=repo)
            except Exception as exc:
                _log.warning("health inspection failed for %s: %s", supervisor_meta.id, exc)
                continue
            if supervisor.meta.status not in {"active", "blocked"}:
                continue
            for child_id in supervisor.meta.children:
                try:
                    child = read_doc(child_id, root=repo)
                    if child.meta.parent != supervisor.meta.id:
                        raise ValueError("direct-report parent mismatch")
                    observation = classify_child(supervisor, child, views.get(child_id))
                except Exception as exc:
                    _log.warning(
                        "health inspection failed for %s/%s: %s",
                        supervisor.meta.id,
                        child_id,
                        exc,
                    )
                    continue
                observations.append(observation)
                if observation.classification == "remediation_eligible":
                    _remediate_if_unchanged(repo, supervisor, child, observation)
                elif observation.classification == "unresolved":
                    propagate_direct_report_blockage(
                        supervisor, child, observation.reason, root=repo
                    )
                else:
                    reconcile_direct_report_blockage(supervisor, child, root=repo)
                # Writes use optimistic tokens. Refresh before considering a
                # sibling so independent causes converge after our own update.
                supervisor = read_doc(supervisor.meta.id, root=repo)
    return observations


def maybe_sweep_supervisor_health(root: Path | None = None) -> list[ChildHealthObservation]:
    """Run a health sweep when the configured cadence is due."""

    repo = resolve_root(root)
    now = time.monotonic()
    with process_lock:
        previous = _last_sweep_at.get(repo)
        if previous is not None and now - previous < supervisor_health_sweep_seconds(repo):
            return []
        _last_sweep_at[repo] = now
    return sweep_supervisor_health(repo)


def clear_health_memory() -> None:
    with process_lock:
        _last_sweep_at.clear()


def _remediate_if_unchanged(
    repo: Path,
    supervisor: WorkDoc,
    child: WorkDoc,
    observation: ChildHealthObservation,
) -> None:
    if child.sha is None:
        _log.warning("cannot remediate %s without a persisted document SHA", child.meta.id)
        return
    key = RemediationIncidentKey(supervisor.meta.id, child.meta.id, child.sha)
    try:
        ledger = _read_ledger(repo)
    except (OSError, ValueError) as exc:
        _log.warning("cannot read remediation ledger for %s: %s", child.meta.id, exc)
        return
    if key.storage_key in ledger:
        return
    try:
        current = read_doc(child.meta.id, root=repo)
    except Exception as exc:
        _log.warning("health revalidation failed for %s: %s", child.meta.id, exc)
        return
    unchanged = (
        current.meta.id == child.meta.id
        and current.meta.parent == supervisor.meta.id
        and current.meta.status == child.meta.status
        and current.meta.path.parent.name == legal_folder(child.meta.status)
        and current.sha == child.sha
    )
    if not unchanged or current.meta.status in {"completed", "cancelled"}:
        return
    disposition = {
        "incident": asdict(key),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "action": "retry_task",
        "result": "claimed",
        "reason": observation.reason,
    }
    ledger[key.storage_key] = disposition
    _write_ledger(repo, ledger)
    try:
        result = retry_task(child.meta.id, feature_id=supervisor.meta.id, root=repo)
        disposition["result"] = "accepted" if result.get("ok") else "refused"
        disposition["reason"] = result.get("reason") or disposition["result"]
    except Exception as exc:
        disposition["result"] = "error"
        disposition["reason"] = f"{type(exc).__name__}: {exc}"
        _log.warning("health remediation failed for %s: %s", child.meta.id, exc)
    finally:
        ledger = _read_ledger(repo)
        ledger[key.storage_key] = disposition
        _write_ledger(repo, ledger)


def _ledger_path(repo: Path) -> Path:
    return repo / ".cascade" / "remediation_dispositions.json"


def _read_ledger(repo: Path) -> dict[str, dict[str, Any]]:
    path = _ledger_path(repo)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid remediation disposition ledger") from exc
    rows = raw.get("dispositions") if isinstance(raw, dict) else None
    if not isinstance(rows, dict):
        return {}
    return {
        str(key): dict(value)
        for key, value in rows.items()
        if isinstance(value, dict)
    }


def _write_ledger(repo: Path, ledger: dict[str, dict[str, Any]]) -> None:
    path = _ledger_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump({"version": 1, "dispositions": ledger}, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def _optional_int(row: dict[str, Any] | None, key: str) -> int | None:
    value = row.get(key) if row else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(row: dict[str, Any] | None, key: str) -> str | None:
    value = row.get(key) if row else None
    return value if isinstance(value, str) else None
