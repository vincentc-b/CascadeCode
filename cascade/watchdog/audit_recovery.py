"""Durable health-audit recovery admission and supervised execution."""

from __future__ import annotations

import logging
import multiprocessing
import os
import queue
import signal
import threading
import time
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from cascade.agent.mcp_project_context import (
    project_context_payload,
    restore_project_context,
)
from cascade.task.action_recovery import recovery_actions
from cascade.watchdog.audit import AuditObservation, project_audit_observation
from cascade.watchdog.capabilities import (
    CapabilityDescriptor,
    CapabilityRegistry,
    default_capability_registry,
    probe_capability,
)
from cascade.watchdog.incidents import incident_record, project_incident
from cascade.watchdog.reservations import (
    IncidentReservation,
    record_result,
    reserve_after_recheck,
)

_log = logging.getLogger(__name__)
_STOP = object()
_ADMISSION_TIMEOUT_SECONDS = 5.0
_ADMISSION_CANCEL_GRACE_SECONDS = 0.1


class AuditRecoveryWorker:
    """Run admitted lifecycle adapters outside the audit scheduler and claim."""

    def __init__(
        self,
        root: Path,
        *,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        # Registry loading binds the existing owner tool registries.  Keep it
        # off supervisor startup's critical path and resolve it in the worker.
        self.registry = registry
        self._stop = threading.Event()
        self._pending: queue.Queue[tuple[str, ...] | object] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run,
            name="health-audit-recovery",
            daemon=True,
        )
        self._thread.start()

    def submit(self, work_ids: tuple[str, ...]) -> None:
        if work_ids:
            self._pending.put(tuple(dict.fromkeys(work_ids)))

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        self._pending.put(_STOP)
        self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            request = self._pending.get()
            try:
                if request is _STOP:
                    return
                assert isinstance(request, tuple)
                for work_id in request:
                    try:
                        dispatch_audit_recovery(
                            self.root,
                            work_id,
                            registry=self.registry,
                            cancel_event=self._stop,
                        )
                    except Exception:
                        # The reservation/probe stores retain actionable evidence;
                        # one broken adapter cannot stop later work items.
                        _log.exception("health-audit recovery failed for %s", work_id)
            finally:
                self._pending.task_done()


def dispatch_audit_recovery(
    root: Path,
    work_id: str,
    *,
    registry: CapabilityRegistry | None = None,
    timeout_seconds: float = _ADMISSION_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
) -> bool:
    """Claim and execute the currently proven incident, if one remains."""

    selected = registry or default_capability_registry()
    admitted = _bounded_admission(
        root,
        work_id,
        selected,
        timeout_seconds=max(0.001, timeout_seconds),
        cancel_event=cancel_event,
    )
    if admitted is None:
        return False
    reservation, descriptor_name, contract, registry_fingerprint = admitted
    owner_kind = str(contract["accountable_owner"]).partition(":")[0]
    descriptor = selected.resolve(
        descriptor_name,
        tier=reservation.tier,  # type: ignore[arg-type]
        owner_kind=owner_kind,  # type: ignore[arg-type]
    )
    # The child has no repair executor. Rebind only the exact capability that
    # the parent supplied and whose complete admission metadata still matches.
    if (
        descriptor is None
        or descriptor.name != descriptor_name
        or selected.fingerprint() != registry_fingerprint
    ):
        return False
    _execute_reservation(reservation, descriptor, contract, root=root)
    return True


def _admission_executor_marker(*_args: object, **_kwargs: object) -> None:
    """Spawn-safe callable proving metadata registration without repair power."""


def _bounded_admission(
    root: Path,
    work_id: str,
    registry: CapabilityRegistry,
    *,
    timeout_seconds: float,
    cancel_event: threading.Event | None,
) -> tuple[IncidentReservation, str, dict[str, Any], str] | None:
    """Run observation, probe and locked reservation in a killable process."""

    context = multiprocessing.get_context("spawn")
    operation_cancel = context.Event()
    receiver, sender = context.Pipe(duplex=False)
    descriptors = tuple(
        replace(descriptor, executor=_admission_executor_marker)
        for descriptor in registry.descriptors()
    )
    worker = context.Process(
        target=_admission_process,
        args=(
            sender,
            Path(root).resolve(),
            work_id,
            descriptors,
            operation_cancel,
            timeout_seconds,
            project_context_payload(),
        ),
        name="health-audit-admission",
        daemon=True,
    )
    deadline = time.monotonic() + timeout_seconds
    worker.start()
    sender.close()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _reap_admission(worker, operation_cancel)
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _reap_admission(worker, operation_cancel)
                return None
            if receiver.poll(min(0.02, remaining)):
                try:
                    succeeded, payload = receiver.recv()
                except EOFError:
                    _reap_admission(worker, operation_cancel, cancel_first=False)
                    return None
                _reap_admission(worker, operation_cancel, cancel_first=False)
                return payload if succeeded else None
            if not worker.is_alive():
                _reap_admission(worker, operation_cancel, cancel_first=False)
                if not receiver.poll(0):
                    return None
                try:
                    succeeded, payload = receiver.recv()
                except EOFError:
                    return None
                return payload if succeeded else None
    finally:
        receiver.close()


def _admission_process(
    sender: Any,
    root: Path,
    work_id: str,
    descriptors: tuple[CapabilityDescriptor, ...],
    cancel_event: Any,
    timeout_seconds: float,
    context_payload: object,
) -> None:
    try:
        os.setsid()
        restore_project_context(context_payload)
        payload = _admit_inline(
            root,
            work_id,
            CapabilityRegistry(descriptors),
            deadline=time.monotonic() + timeout_seconds,
            cancel_event=cancel_event,
        )
        message = (True, payload)
    except BaseException as exc:
        message = (False, (type(exc).__name__, str(exc)))
    try:
        sender.send(message)
    except Exception:
        pass
    finally:
        sender.close()


def _reap_admission(
    worker: multiprocessing.Process,
    cancel_event: Any,
    *,
    cancel_first: bool = True,
) -> None:
    if cancel_first:
        cancel_event.set()
    worker.join(timeout=_ADMISSION_CANCEL_GRACE_SECONDS)
    if worker.is_alive():
        _signal_admission_group(worker, signal.SIGTERM)
        worker.join(timeout=_ADMISSION_CANCEL_GRACE_SECONDS)
    if worker.is_alive():
        _signal_admission_group(worker, signal.SIGKILL)
        worker.join(timeout=_ADMISSION_CANCEL_GRACE_SECONDS)
    if worker.is_alive():
        raise RuntimeError("health audit admission process could not be reaped")
    _signal_admission_group(worker, signal.SIGKILL)


def _signal_admission_group(
    worker: multiprocessing.Process, sig: signal.Signals
) -> None:
    if worker.pid is None:
        return
    try:
        os.killpg(worker.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        if worker.is_alive():
            try:
                os.kill(worker.pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass


def _admit_inline(
    root: Path,
    work_id: str,
    selected: CapabilityRegistry,
    *,
    deadline: float,
    cancel_event: threading.Event | Any,
) -> tuple[IncidentReservation, str, dict[str, Any], str] | None:
    observation = _bounded_observation(
        work_id, root=root, deadline=deadline, cancel_event=cancel_event
    )
    target = _repair_target(
        observation, root=root, deadline=deadline, cancel_event=cancel_event
    )
    if target is None:
        return None
    if target is not observation:
        observation = target
    contract = _incident_contract(observation, root=root)
    if contract is None:
        return None

    # This cheap projection suppresses completed action-backed generations.
    # The atomic reservation remains the authority for every durable store and
    # for races with parent/manual recovery.
    if not project_incident(
        str(contract["authoritative_generation"]),
        recovery_actions(root=root),
        failure_class=str(contract["failure_class"]),
    ).eligible:
        return None

    owner = str(contract["accountable_owner"])
    probe = probe_capability(
        contract, owner, root=root, registry=selected, persist=True
    )
    if not probe.available:
        return None
    owner_kind = owner.partition(":")[0]
    descriptor = selected.resolve(
        probe.capability,
        tier=observation.tier,
        owner_kind=owner_kind,  # type: ignore[arg-type]
    )
    if descriptor is None:
        return None
    decision = reserve_after_recheck(
        contract,
        descriptor,
        root=root,
        timeout_seconds=max(0.001, deadline - time.monotonic()),
        cancel_event=cancel_event,
    )
    if decision.reservation is None:
        return None
    return (
        decision.reservation,
        descriptor.name,
        contract,
        selected.fingerprint(),
    )


def _repair_target(
    observation: AuditObservation,
    *,
    root: Path,
    deadline: float,
    cancel_event: threading.Event | None,
) -> AuditObservation | None:
    if observation.classification != "proven_incident":
        return None
    if observation.reason.startswith("child:"):
        child_id = observation.reason.split(":", 2)[1]
        child = _bounded_observation(
            child_id, root=root, deadline=deadline, cancel_event=cancel_event
        )
        return child if child.classification == "proven_incident" else None
    return observation


def _bounded_observation(
    work_id: str,
    *,
    root: Path,
    deadline: float,
    cancel_event: threading.Event | None,
) -> AuditObservation:
    """Project one admission candidate within the worker's shared budget."""

    return project_audit_observation(
        work_id,
        root=root,
        timeout_seconds=max(0.001, deadline - time.monotonic()),
        cancel_event=cancel_event,
    )


def _incident_contract(
    observation: AuditObservation, *, root: Path
) -> dict[str, Any] | None:
    incident = observation.incident
    if incident is None:
        return None
    evidence = _evidence(observation)
    failure = incident.failure_class
    parent_id = observation.evidence.parent_id
    operation: str | None = None
    owner: str | None = None

    if observation.tier == "task" and parent_id:
        owner = f"feature_team:{parent_id}"
        if failure == "blocked_task_failed":
            operation = "retry_task"
        elif failure in {"stalled_execution", "delivery_reconciliation"}:
            operation = "supervisor_recover_task_delivery"

    if operation is None and failure == "integration_branch_update":
        action = _integration_action(observation, root=root)
        if action is not None:
            recovery = action.get("recovery")
            owning_team = (
                recovery.get("owning_team") if isinstance(recovery, Mapping) else None
            )
            if isinstance(owning_team, Mapping):
                kind, owner_id = owning_team.get("kind"), owning_team.get("work_id")
                if kind in {"feature_team", "epic_team"} and isinstance(owner_id, str):
                    owner = f"{kind}:{owner_id}"
                    operation = "retry_integration_branch_update"
                    evidence["action_id"] = action.get("action_id")

    if operation is None or owner is None:
        return None
    return incident_record(
        work_id=str(observation.work_id),
        tier=observation.tier,
        accountable_owner=owner,
        failure_class=failure,
        generation=str(observation.generation),
        evidence=evidence,
        selected_capability=operation,
        outcome="deferred",
    )


def _evidence(observation: AuditObservation) -> dict[str, Any]:
    identity = observation.identity
    source = observation.evidence
    return {
        "document_revision": (
            str(identity.document_revision) if identity.document_revision else None
        ),
        "git_head": str(identity.git_head) if identity.git_head else None,
        "branch": str(identity.branch) if identity.branch else None,
        "status": source.status,
        "parent_id": source.parent_id,
        "execution": dict(source.execution) if source.execution else None,
        "gates": list(source.gates),
        "unresolved_references": list(source.unresolved_references),
        "local_fingerprint": source.local_fingerprint,
        "reason": observation.reason,
    }


def _integration_action(
    observation: AuditObservation, *, root: Path
) -> Mapping[str, Any] | None:
    references = set(observation.evidence.unresolved_references)
    return next(
        (
            row
            for row in recovery_actions(root=root)
            if row.get("action_kind") == "integration_branch_update"
            and row.get("action_id") in references
        ),
        None,
    )


def _execute_reservation(
    reservation: IncidentReservation,
    descriptor: CapabilityDescriptor,
    contract: Mapping[str, Any],
    *,
    root: Path,
) -> None:
    executor = descriptor.executor
    assert executor is not None
    owner_kind, _, owner_id = str(contract["accountable_owner"]).partition(":")
    evidence = contract["evidence"]
    try:
        # Recovery adapters may dispatch a roster turn. Queue that turn on its
        # existing per-graph worker so this single admission worker remains
        # free to acknowledge claims and process later incidents.
        from cascade.workspace.kickoff import deferred_kickoffs

        with deferred_kickoffs():
            if descriptor.operation == "supervisor_recover_task_delivery":
                value = executor(
                    reservation.work_id,
                    root=root,
                    observed_incident=reservation.reservation_id,
                )
            elif descriptor.operation in {"retry_task", "recover_task"}:
                value = executor(reservation.work_id, feature_id=owner_id, root=root)
            elif descriptor.operation == "retry_integration_branch_update":
                owner_arg = "feature_id" if owner_kind == "feature_team" else "epic_id"
                value = executor(
                    str(evidence["action_id"]), root=root, **{owner_arg: owner_id}
                )
            else:
                raise RuntimeError(
                    f"unsupported audit recovery operation: {descriptor.operation}"
                )
        payload = _result_payload(value)
        outcome = _result_outcome(value)
    except Exception as exc:
        payload = {"error": type(exc).__name__, "message": str(exc)}
        outcome = "error"
    record_result(
        reservation,
        {"worker": "health-audit-recovery", "accepted": True},
        {"outcome": outcome, **payload},
        root=root,
    )


def _result_payload(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {"adapter_result": dict(value)}
    if is_dataclass(value):
        return {"adapter_result": asdict(value)}
    return {"adapter_result": {"value": str(value)}}


def _result_outcome(value: object) -> str:
    if isinstance(value, Mapping):
        return "success" if value.get("ok", True) else "refused"
    decision = getattr(value, "decision", None)
    if decision == "unsafe":
        return "unsafe"
    if decision == "defer_draining":
        return "deferred"
    if decision in {"no_op_live_owner", "already_delivered"}:
        return "no_op"
    return "success"


__all__ = ["AuditRecoveryWorker", "dispatch_audit_recovery"]
