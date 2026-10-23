"""Synthetic Epic → Feature → Task lifecycle exercises (feat_012_003 / task_012_003_002)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cascade.probe.harness import ProbeWorkspace
from cascade.probe.report import LifecycleProbeReport, ProbePhaseResult, merge_phase_results
from cascade.probe.runtime import isolated_probe_scenario
from cascade.probe.seed import seed_dispatchable_feature, seed_lifecycle_chain
from cascade.watchdog.types import Event
from cascade.workspace.convergence import (
    observe_convergence_states,
    set_convergence_clock_for_tests,
)
from cascade.workspace.supervisor_readiness import (
    observe_startup_phase,
    read_supervisor_health_projection,
    record_loop_started,
    record_loop_success,
    reset_supervisor_readiness_for_tests,
)
from cascade.workspace.supervisor_status import utc_now_iso, write_supervisor_status


def _stall_toasts(root: Path, *, work_id: str | None = None) -> list[Event]:
    from cascade.watchdog.events import read_events

    events, _ = read_events("war_room", 0, root=root)
    toasts = [
        event
        for event in events
        if event.type == "Toast" and event.payload.get("kind") == "convergence_stall"
    ]
    if work_id is None:
        return toasts
    return [event for event in toasts if event.payload.get("id") == work_id]


def _exercise_success_path(
    root: Path,
    *,
    deadline_check: Callable[..., None],
) -> tuple[ProbePhaseResult, ...]:
    from cascade.boss.view import compute_boss_view
    from cascade.watchdog.dispatch import activate_epic, dispatch_feature, dispatch_task
    from cascade.watchdog.loop import watchdog_tick

    ids = seed_lifecycle_chain(root)
    deadline_check(phase="synthetic lifecycle seed")

    dispatch_phases: list[ProbePhaseResult] = []
    epic = activate_epic(ids["epic"], "human", root=root)
    feature = dispatch_feature(ids["feature"], "human", root=root)
    task = dispatch_task(ids["task"], "human", root=root)
    chain_ok = epic.ok and feature.ok and task.ok
    dispatch_phases.append(
        ProbePhaseResult(
            phase="synthetic_lifecycle",
            ok=chain_ok,
            detail="" if chain_ok else f"epic={epic.reason} feature={feature.reason} task={task.reason}",
        )
    )
    if not chain_ok:
        return tuple(dispatch_phases)

    reset_supervisor_readiness_for_tests()
    now = utc_now_iso()
    write_supervisor_status(
        root,
        {
            "state": "serving",
            "worker_pid": 1,
            "restart_count": 0,
            "last_error": None,
            "next_action": None,
            "trunk_lock_warning": None,
            "since": now,
            "updated_at": now,
        },
    )
    observe_startup_phase("ready")
    record_loop_started("reconciliation")
    record_loop_success("reconciliation", at=now)
    record_loop_started("watchdog")
    record_loop_success("watchdog", at=now)
    health = read_supervisor_health_projection(root, http_serving=True)
    readiness_ok = health is not None and health.get("automation", {}).get("ready") is True
    dispatch_phases.append(
        ProbePhaseResult(
            phase="readiness_transitions",
            ok=readiness_ok,
            detail="" if readiness_ok else "automation not ready after loop evidence",
        )
    )

    seed_dispatchable_feature(
        root,
        epic_id="epic_902",
        feature_id="feat_902",
        stall_threshold_seconds=60.0,
    )
    clock = {"t": 100.0}
    set_convergence_clock_for_tests(lambda: clock["t"])
    deadline_check(phase="watchdog convergence seed")

    try:
        watchdog_tick(root)
    except Exception as exc:
        dispatch_phases.append(
            ProbePhaseResult(
                phase="watchdog_reconciliation",
                ok=False,
                detail=str(exc),
            )
        )
        return tuple(dispatch_phases)

    dispatch_phases.append(
        ProbePhaseResult(
            phase="watchdog_reconciliation",
            ok=True,
            detail="watchdog_tick completed",
        )
    )

    view = compute_boss_view(root=root)
    observations = observe_convergence_states(root=root)
    conv = next((obs for obs in observations if obs.work_id == "feat_902"), None)
    progressing_ok = (
        "feat_902" in view.dispatchable_features
        and conv is not None
        and conv.state == "progressing"
        and _stall_toasts(root) == []
    )
    dispatch_phases.append(
        ProbePhaseResult(
            phase="convergence_detection",
            ok=progressing_ok,
            detail=""
            if progressing_ok
            else f"state={getattr(conv, 'state', None)} toasts={len(_stall_toasts(root))}",
        )
    )
    return tuple(dispatch_phases)


def _exercise_stall_and_recovery(
    root: Path,
    *,
    deadline_check: Callable[..., None],
) -> tuple[ProbePhaseResult, ...]:
    from cascade.watchdog.events import append_event
    from cascade.watchdog.loop import watchdog_tick
    from cascade.workspace.convergence import (
        clear_convergence_diagnostic_memory,
        reset_convergence_detection_for_tests,
    )

    reset_supervisor_readiness_for_tests()
    reset_convergence_detection_for_tests()
    clear_convergence_diagnostic_memory()
    stall_id = "feat_903"
    seed_dispatchable_feature(
        root,
        epic_id="epic_903",
        feature_id="feat_903",
        stall_threshold_seconds=10.0,
    )
    clock = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: clock["t"])
    results: list[ProbePhaseResult] = []

    watchdog_tick(root)
    clock["t"] = 100.0
    watchdog_tick(root)
    toasts = _stall_toasts(root, work_id=stall_id)
    stall_ok = len(toasts) == 1 and toasts[0].payload.get("id") == stall_id
    results.append(
        ProbePhaseResult(
            phase="intentional_stall",
            ok=stall_ok,
            detail="" if stall_ok else f"toast_count={len(toasts)}",
        )
    )

    diagnostic_ok = (
        stall_ok
        and toasts[0].payload.get("kind") == "convergence_stall"
        and toasts[0].payload.get("blocker") == "no_durable_progress"
    )
    results.append(
        ProbePhaseResult(
            phase="stall_diagnostic",
            ok=diagnostic_ok,
            detail="" if diagnostic_ok else "missing convergence_stall durable diagnostic",
        )
    )
    if not stall_ok:
        return tuple(results)

    append_event(
        stall_id,
        Event(
            type="FeatureReadyToPlan",
            ts=datetime.now(timezone.utc),
            payload={"id": stall_id},
            dest=stall_id,
        ),
        root=root,
    )
    watchdog_tick(root)
    after_progress = _stall_toasts(root, work_id=stall_id)
    recovery_ok = len(after_progress) == 1
    results.append(
        ProbePhaseResult(
            phase="stall_recovery",
            ok=recovery_ok,
            detail="" if recovery_ok else f"toast_count={len(after_progress)}",
        )
    )

    clock["t"] = 200.0
    watchdog_tick(root)
    re_stall_ok = len(_stall_toasts(root, work_id=stall_id)) == 2
    results.append(
        ProbePhaseResult(
            phase="stall_re_emit",
            ok=re_stall_ok,
            detail=""
            if re_stall_ok
            else f"toast_count={len(_stall_toasts(root, work_id=stall_id))}",
        )
    )
    return tuple(results)


def run_lifecycle_probe(workspace: ProbeWorkspace) -> LifecycleProbeReport:
    """Drive success and intentional-stall scenarios inside ``workspace``."""

    root = workspace.root
    workspace.validate_mutation_target(root)

    def deadline_check(*, phase: str) -> None:
        workspace.deadline.check(phase=phase)

    with isolated_probe_scenario():
        success = _exercise_success_path(root, deadline_check=deadline_check)
        stall = _exercise_stall_and_recovery(root, deadline_check=deadline_check)
    return merge_phase_results(success, stall)
