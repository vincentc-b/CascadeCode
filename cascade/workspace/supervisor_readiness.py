"""Authoritative read-only supervisor readiness projection (feat_012_001 / task_012_001_001).

Startup, watchdog, and lifecycle-reconciliation code publish process-local evidence;
``project_supervisor_health`` merges that with ``supervisor_status.json`` for operators.
Observation and projection must not dispatch work or mutate board lifecycle state.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypedDict

from cascade.workspace.supervisor_status import (
    SupervisorState,
    SupervisorStatus,
    read_supervisor_status,
    utc_now_iso,
)

StartupPhase = Literal[
    "starting",
    "http_serving",
    "recovery",
    "watchdog",
    "ready",
]

LoopName = Literal["watchdog", "reconciliation"]


class LoopLastError(TypedDict, total=False):
    code: str
    message: str
    at: str


class LoopActivity(TypedDict, total=False):
    last_started_at: str | None
    last_success_at: str | None
    last_error: LoopLastError | None


class HttpLiveness(TypedDict):
    live: bool


class RecoveryFailure(TypedDict):
    work_id: str
    code: str
    message: str
    at: str


class RecoveryProgress(TypedDict):
    in_flight: int
    failures: list[RecoveryFailure]


class AutomationReadiness(TypedDict):
    ready: bool
    phase: StartupPhase
    degraded_reasons: list[str]


class LoopBundle(TypedDict):
    watchdog: LoopActivity
    reconciliation: LoopActivity


class SupervisorHealthProjection(TypedDict, total=False):
    state: SupervisorState
    worker_pid: int | None
    restart_count: int
    last_error: dict[str, object] | None
    next_action: str | None
    trunk_lock_warning: str | None
    since: str
    updated_at: str
    http: HttpLiveness
    automation: AutomationReadiness
    loops: LoopBundle
    recovery: RecoveryProgress


@dataclass
class _LoopEvidence:
    last_started_at: str | None = None
    last_success_at: str | None = None
    last_error: LoopLastError | None = None


@dataclass
class SupervisorReadinessEvidence:
    """Mutable process-local recorder state (worker only)."""

    startup_phase: StartupPhase = "starting"
    http_live: bool = False
    watchdog: _LoopEvidence = field(default_factory=_LoopEvidence)
    reconciliation: _LoopEvidence = field(default_factory=_LoopEvidence)
    recovery_in_flight: int = 0
    recovery_failures: list[RecoveryFailure] = field(default_factory=list)

    def has_signal(self) -> bool:
        return self.http_live or self.startup_phase != "starting" or bool(
            self.watchdog.last_started_at
            or self.watchdog.last_success_at
            or self.reconciliation.last_started_at
            or self.reconciliation.last_success_at
            or self.recovery_in_flight
            or self.recovery_failures
        )


_lock = threading.Lock()
_evidence = SupervisorReadinessEvidence()
_recovery_work_ids: set[str] = set()


def reset_supervisor_readiness_for_tests() -> None:
    """Clear in-process evidence (tests only)."""

    global _evidence
    with _lock:
        _evidence = SupervisorReadinessEvidence()
        _recovery_work_ids.clear()


def snapshot_readiness_evidence() -> SupervisorReadinessEvidence:
    with _lock:
        wd = _evidence.watchdog
        rc = _evidence.reconciliation
        return SupervisorReadinessEvidence(
            startup_phase=_evidence.startup_phase,
            http_live=_evidence.http_live,
            watchdog=_LoopEvidence(
                last_started_at=wd.last_started_at,
                last_success_at=wd.last_success_at,
                last_error=(
                    dict(_evidence.watchdog.last_error)
                    if wd.last_error is not None
                    else None
                ),
            ),
            reconciliation=_LoopEvidence(
                last_started_at=rc.last_started_at,
                last_success_at=rc.last_success_at,
                last_error=(
                    dict(_evidence.reconciliation.last_error)
                    if rc.last_error is not None
                    else None
                ),
            ),
            recovery_in_flight=_evidence.recovery_in_flight,
            recovery_failures=[dict(row) for row in _evidence.recovery_failures],
        )


def observe_http_live(*, live: bool) -> None:
    with _lock:
        _evidence.http_live = live
        if live and _evidence.startup_phase == "starting":
            _evidence.startup_phase = "http_serving"


def observe_startup_phase(phase: StartupPhase) -> None:
    with _lock:
        _evidence.startup_phase = phase


def record_recovery_enqueued(work_id: str) -> None:
    """Mark a graph whose recovered turn was queued during startup recovery."""

    with _lock:
        _recovery_work_ids.add(work_id)


def note_recovery_turn_started(work_id: str) -> None:
    with _lock:
        if work_id not in _recovery_work_ids:
            return
        _evidence.recovery_in_flight += 1


def note_recovery_turn_finished(work_id: str) -> None:
    with _lock:
        if work_id not in _recovery_work_ids:
            return
        _recovery_work_ids.discard(work_id)
        if _evidence.recovery_in_flight > 0:
            _evidence.recovery_in_flight -= 1


def record_recovery_failure(
    work_id: str,
    *,
    code: str,
    message: str,
    at: str | None = None,
) -> None:
    stamp = at or utc_now_iso()
    failure: RecoveryFailure = {
        "work_id": work_id,
        "code": code,
        "message": message,
        "at": stamp,
    }
    with _lock:
        if work_id not in _recovery_work_ids:
            return
        _recovery_work_ids.discard(work_id)
        if _evidence.recovery_in_flight > 0:
            _evidence.recovery_in_flight -= 1
        _evidence.recovery_failures.append(failure)


def record_loop_started(loop: LoopName, *, at: str | None = None) -> None:
    stamp = at or utc_now_iso()
    with _lock:
        target = _evidence.watchdog if loop == "watchdog" else _evidence.reconciliation
        target.last_started_at = stamp


def record_loop_success(loop: LoopName, *, at: str | None = None) -> None:
    stamp = at or utc_now_iso()
    with _lock:
        target = _evidence.watchdog if loop == "watchdog" else _evidence.reconciliation
        target.last_success_at = stamp
        target.last_error = None
        if loop == "watchdog" and _evidence.startup_phase == "watchdog":
            _evidence.startup_phase = "ready"


def record_loop_error(
    loop: LoopName,
    *,
    code: str,
    message: str,
    at: str | None = None,
) -> None:
    stamp = at or utc_now_iso()
    err: LoopLastError = {"code": code, "message": message, "at": stamp}
    with _lock:
        target = _evidence.watchdog if loop == "watchdog" else _evidence.reconciliation
        target.last_error = err


def _loop_activity(evidence: _LoopEvidence) -> LoopActivity:
    return {
        "last_started_at": evidence.last_started_at,
        "last_success_at": evidence.last_success_at,
        "last_error": evidence.last_error,
    }


def _supervisor_degraded_reasons(
    status: SupervisorStatus | None,
) -> list[str]:
    if status is None:
        return []
    state = status.get("state")
    if state in ("degraded", "restarting", "update_blocked"):
        return [f"supervisor:{state}"]
    return []


def _automation_readiness(
    evidence: SupervisorReadinessEvidence,
    status: SupervisorStatus | None,
) -> AutomationReadiness:
    reasons = _supervisor_degraded_reasons(status)
    phase = evidence.startup_phase

    if phase != "ready":
        reasons.append(f"startup:{phase}")
    if evidence.watchdog.last_success_at is None:
        reasons.append("watchdog:no_success_yet")
    if evidence.reconciliation.last_success_at is None:
        reasons.append("reconciliation:no_success_yet")
    for failure in evidence.recovery_failures:
        reasons.append(f"recovery:{failure['work_id']}:{failure['code']}")

    # Stable order for tests and UI diffs.
    reasons = list(dict.fromkeys(reasons))
    ready = not reasons
    return {"ready": ready, "phase": phase, "degraded_reasons": reasons}


def project_supervisor_health(
    status: SupervisorStatus | None,
    evidence: SupervisorReadinessEvidence,
    *,
    http_serving: bool = False,
) -> SupervisorHealthProjection | None:
    """Return an immutable health dict; None only when there is no status and no HTTP signal."""

    http_live = evidence.http_live or http_serving
    if status is None and not http_live and not evidence.has_signal():
        return None

    automation = _automation_readiness(evidence, status)
    loops: LoopBundle = {
        "watchdog": _loop_activity(evidence.watchdog),
        "reconciliation": _loop_activity(evidence.reconciliation),
    }
    recovery: RecoveryProgress = {
        "in_flight": evidence.recovery_in_flight,
        "failures": [dict(row) for row in evidence.recovery_failures],
    }
    projection: SupervisorHealthProjection = {
        "http": {"live": http_live},
        "automation": automation,
        "loops": loops,
        "recovery": recovery,
    }
    if status is not None:
        projection.update(status)  # type: ignore[typeddict-item]
    return projection


def read_supervisor_health_projection(
    workspace_root: Path,
    *,
    http_serving: bool = False,
    status: SupervisorStatus | None = None,
) -> SupervisorHealthProjection | None:
    """Read-only merge of on-disk supervisor status and in-process readiness evidence."""

    if status is None:
        status = read_supervisor_status(workspace_root)
    evidence = snapshot_readiness_evidence()
    return project_supervisor_health(status, evidence, http_serving=http_serving)


def supervisor_health_http_payload(
    workspace_root: Path,
    *,
    http_serving: bool,
    status: SupervisorStatus | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """Authoritative JSON body for War Room and launcher health responses."""

    payload_obj = read_supervisor_health_projection(
        workspace_root,
        http_serving=http_serving,
        status=status,
    )
    if payload_obj is None:
        payload: dict[str, object] = {"error": error or "degraded", "state": "degraded"}
    else:
        payload = dict(payload_obj)
        if error is not None:
            payload["error"] = error
    return payload
