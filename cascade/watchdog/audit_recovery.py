"""Durable health-audit recovery admission and supervised execution."""

from __future__ import annotations

import logging
import multiprocessing
import os
import queue
import signal
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from cascade.agent.mcp_project_context import (
    project_context_payload,
    restore_project_context,
)
from cascade.board.gitutil import inherited_git_process_group
from cascade.board.store import read_doc
from cascade.task.action_recovery import recovery_actions
from cascade.task.lifecycle_lock import lifecycle_root
from cascade.watchdog.audit import (
    AuditObservation,
    _restore_parent_observation_episodes,
    _snapshot_parent_observation_episodes,
    project_audit_observation,
)
from cascade.watchdog.capabilities import (
    CapabilityDescriptor,
    CapabilityRegistry,
    default_capability_registry,
    probe_capability,
)
from cascade.watchdog.incidents import incident_record, project_incident
from cascade.watchdog.reservations import (
    IncidentReservation,
    _record_unstarted_claim,
    accept_claim,
    record_interrupted_claim,
    record_result,
    reserve_after_recheck,
)

_log = logging.getLogger(__name__)
_STOP = object()
_ADMISSION_TIMEOUT_SECONDS = 15.0
_ADMISSION_CANCEL_GRACE_SECONDS = 0.1
_ADMISSION_RECONCILE_SECONDS = 5.0


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
    deadline = time.monotonic() + max(0.001, timeout_seconds)
    admitted = _bounded_admission(
        root,
        work_id,
        selected,
        deadline=deadline,
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
        _reconcile_interrupted_claim(
            root, reservation.claim_token, (reservation.durable_store,)
        )
        return False
    if not _bounded_accept_claim(
        root,
        reservation,
        deadline=deadline,
        cancel_event=cancel_event,
    ):
        _reconcile_interrupted_claim(
            root,
            reservation.claim_token,
            (reservation.durable_store,),
            accepted_handoff=True,
        )
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
    deadline: float,
    cancel_event: threading.Event | None,
) -> tuple[IncidentReservation, str, dict[str, Any], str] | None:
    """Run observation, probe and locked reservation in a killable process."""

    context = multiprocessing.get_context("spawn")
    operation_cancel = context.Event()
    receiver, sender = context.Pipe(duplex=False)
    claim_token = uuid.uuid4().hex
    durable_stores = tuple(
        dict.fromkeys(descriptor.durable_store for descriptor in registry.descriptors())
    )
    descriptors = tuple(
        replace(
            descriptor,
            executor=(
                _admission_executor_marker if callable(descriptor.executor) else None
            ),
        )
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
            deadline,
            project_context_payload(),
            claim_token,
            _snapshot_parent_observation_episodes(),
        ),
        name="health-audit-admission",
        daemon=True,
    )
    worker.start()
    sender.close()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _reap_admission(worker, operation_cancel)
                _reconcile_interrupted_claim(root, claim_token, durable_stores)
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _reap_admission(worker, operation_cancel)
                _reconcile_interrupted_claim(root, claim_token, durable_stores)
                return None
            if receiver.poll(min(0.02, remaining)):
                try:
                    succeeded, payload = receiver.recv()
                except EOFError:
                    _reap_admission(worker, operation_cancel, cancel_first=False)
                    _reconcile_interrupted_claim(root, claim_token, durable_stores)
                    return None
                _reap_admission(worker, operation_cancel, cancel_first=False)
                if not succeeded:
                    _reconcile_interrupted_claim(root, claim_token, durable_stores)
                    return None
                return payload
            if not worker.is_alive():
                _reap_admission(worker, operation_cancel, cancel_first=False)
                if not receiver.poll(0):
                    _reconcile_interrupted_claim(root, claim_token, durable_stores)
                    return None
                try:
                    succeeded, payload = receiver.recv()
                except EOFError:
                    _reconcile_interrupted_claim(root, claim_token, durable_stores)
                    return None
                if not succeeded:
                    _reconcile_interrupted_claim(root, claim_token, durable_stores)
                    return None
                return payload
    finally:
        receiver.close()


def _bounded_accept_claim(
    root: Path,
    reservation: IncidentReservation,
    *,
    deadline: float,
    cancel_event: threading.Event | None,
) -> bool:
    """Accept a child reservation without blocking the supervisor worker."""

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(
        target=_accept_claim_process,
        args=(
            sender,
            Path(root).resolve(),
            reservation,
            project_context_payload(),
        ),
        name="health-audit-admission-accept",
        daemon=True,
    )
    worker.start()
    sender.close()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _reap_admission(worker, context.Event())
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _reap_admission(worker, context.Event())
                return False
            if receiver.poll(min(0.02, remaining)):
                try:
                    accepted = receiver.recv()
                except EOFError:
                    accepted = False
                _reap_admission(worker, context.Event(), cancel_first=False)
                return accepted is True
            if not worker.is_alive():
                _reap_admission(worker, context.Event(), cancel_first=False)
                try:
                    return receiver.poll(0) and receiver.recv() is True
                except EOFError:
                    return False
    finally:
        receiver.close()


def _accept_claim_process(
    sender: Any,
    root: Path,
    reservation: IncidentReservation,
    context_payload: object,
) -> None:
    try:
        os.setsid()
        restore_project_context(context_payload)
        accepted = accept_claim(reservation, root=root)
        sender.send(accepted)
    except BaseException:
        pass
    finally:
        sender.close()


def _admission_process(
    sender: Any,
    root: Path,
    work_id: str,
    descriptors: tuple[CapabilityDescriptor, ...],
    cancel_event: Any,
    deadline: float,
    context_payload: object,
    claim_token: str,
    parent_observation_episodes: tuple[
        tuple[str, str, str, str, float, int], ...
    ],
) -> None:
    try:
        os.setsid()
        restore_project_context(context_payload)
        _restore_parent_observation_episodes(parent_observation_episodes)
        with inherited_git_process_group():
            payload = _admit_inline(
                root,
                work_id,
                CapabilityRegistry(descriptors),
                deadline=deadline,
                cancel_event=cancel_event,
                claim_token=claim_token,
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


def _reconcile_interrupted_claim(
    root: Path,
    claim_token: str,
    durable_stores: tuple[str, ...],
    *,
    accepted_handoff: bool = False,
) -> None:
    """Bound exact-token cleanup after the admission child has been reaped."""

    if not durable_stores:
        return
    filenames = {
        "action_recovery": "executions.json",
        "orphan_delivery": "orphan_delivery_recoveries.json",
        "remediation_dispositions": "remediation_dispositions.json",
    }
    lifecycle_repo = lifecycle_root(root)
    sidecars = lifecycle_repo / ".cascade"
    if not any(
        (sidecars / filenames[store]).exists()
        for store in durable_stores
        if store in filenames
    ):
        return
    context = multiprocessing.get_context("spawn")
    worker = context.Process(
        target=_reconcile_claim_process,
        args=(
            lifecycle_repo,
            claim_token,
            durable_stores,
            project_context_payload(),
            accepted_handoff,
        ),
        name="health-audit-admission-reconcile",
        daemon=True,
    )
    worker.start()
    worker.join(timeout=_ADMISSION_RECONCILE_SECONDS)
    # A timed join alone leaves a blocked thread/process behind. Reap before
    # the recovery worker advances to another item, even on a local lock/FIFO.
    _reap_admission(worker, context.Event(), cancel_first=False)
    worker.close()


def _reconcile_claim_process(
    root: Path,
    claim_token: str,
    durable_stores: tuple[str, ...],
    context_payload: object,
    accepted_handoff: bool,
) -> None:
    os.setsid()
    restore_project_context(context_payload)
    if accepted_handoff:
        _record_unstarted_claim(
            claim_token,
            durable_stores,
            root=root,
            accepted_handoff=True,
        )
    else:
        record_interrupted_claim(claim_token, durable_stores, root=root)


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
    claim_token: str | None = None,
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
        claim_token=claim_token,
        handoff_pending=True,
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
        elif failure in {
            "stalled_execution",
            "delivery_reconciliation",
            "validated_delivery_missing",
        }:
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

    parent_action = observation.evidence.parent_action
    if (
        operation is None
        and observation.tier in {"feature", "epic"}
        and parent_action is not None
        and parent_action.state == "executable"
        and parent_action.responsible_work_id == str(observation.work_id)
    ):
        candidate = parent_action.candidate_action
        operation = candidate
        if candidate.startswith("restore_child_dispatch:"):
            operation, _, child_id = candidate.partition(":")
            evidence["child_id"] = child_id
        if operation in {
            "resume_planning_owner",
            "restore_child_dispatch",
            "publish_integration_review",
            "reconcile_completion_rollup",
        }:
            owner = f"{observation.tier}_team:{observation.work_id}"
        else:
            operation = None

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
    evidence = {
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
    if source.parent_action is not None:
        evidence["parent_action"] = {
            "responsible_work_id": source.parent_action.responsible_work_id,
            "candidate_action": source.parent_action.candidate_action,
            "state": source.parent_action.state,
            "reason": source.parent_action.reason,
            "observation_count": source.parent_action.observation_count,
            "unchanged_for_seconds": source.parent_action.unchanged_for_seconds,
            "required_interval_seconds": source.parent_action.required_interval_seconds,
        }
    return evidence


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
                    feature_id=owner_id,
                )
            elif descriptor.operation in {"retry_task", "recover_task"}:
                value = executor(reservation.work_id, feature_id=owner_id, root=root)
            elif descriptor.operation == "retry_integration_branch_update":
                owner_arg = "feature_id" if owner_kind == "feature_team" else "epic_id"
                value = executor(
                    str(evidence["action_id"]), root=root, **{owner_arg: owner_id}
                )
            elif descriptor.name == "feature.resume_planning_owner":
                value = executor(owner_id, generation=reservation.generation, root=root)
            elif descriptor.name == "feature.restore_child_dispatch":
                value = executor(
                    str(evidence["child_id"]),
                    feature_id=owner_id,
                    generation=reservation.generation,
                    root=root,
                )
            elif descriptor.name in {
                "feature.publish_integration_review",
                "feature.reconcile_completion_rollup",
            }:
                value = executor(owner_id, generation=reservation.generation, root=root)
            elif descriptor.name == "epic.resume_planning_owner":
                value = executor(
                    reservation.reservation_id,
                    epic_id=owner_id,
                    expected_generation=reservation.generation,
                    root=root,
                )
            elif descriptor.name == "epic.restore_child_dispatch":
                value = executor(
                    str(evidence["child_id"]),
                    epic_id=owner_id,
                    expected_generation=reservation.generation,
                    root=root,
                )
            elif descriptor.name in {
                "epic.publish_integration_review",
                "epic.reconcile_completion_rollup",
            }:
                value = executor(
                    epic_id=owner_id,
                    expected_generation=reservation.generation,
                    root=root,
                )
            else:
                raise RuntimeError(
                    f"unsupported audit recovery operation: {descriptor.operation}"
                )
        payload = _result_payload(value)
        outcome = _result_outcome(value, reservation=reservation)
    except Exception as exc:
        payload = {"error": type(exc).__name__, "message": str(exc)}
        outcome = "error"
    recorded = record_result(
        reservation,
        {"worker": "health-audit-recovery", "accepted": True},
        {"outcome": outcome, **payload},
        root=root,
    )
    if recorded.get("outcome") == "success":
        _reconcile_exact_blocker(reservation, root=root)


def _result_payload(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {"adapter_result": dict(value)}
    if is_dataclass(value):
        return {"adapter_result": asdict(value)}
    return {"adapter_result": {"value": str(value)}}


def _result_outcome(value: object, *, reservation: IncidentReservation) -> str:
    if isinstance(value, Mapping):
        if value.get("durable_result") is True:
            return "success"
        state = value.get("state")
        if state in {"pending", "review_pending", "retryable", "dispatched"}:
            postcheck = value.get("postcheck")
            if (
                value.get("ok") is True
                and isinstance(postcheck, Mapping)
                and postcheck.get("available") is True
                and (
                    postcheck.get("generation") != reservation.generation
                    or postcheck.get("classification") != "proven_incident"
                )
            ):
                return "success"
            return "deferred"
        if value.get("durable_result") is False:
            return "deferred"
        return "success" if value.get("ok", True) else "refused"
    decision = getattr(value, "decision", None)
    if decision == "unsafe":
        return "unsafe"
    if decision == "defer_draining":
        return "deferred"
    if decision in {"no_op_live_owner", "already_delivered"}:
        return "no_op"
    return "success"


def _reconcile_exact_blocker(
    reservation: IncidentReservation, *, root: Path
) -> None:
    """Clear only a derived parent blocker carrying this result identity."""

    try:
        child = read_doc(reservation.work_id, root=root)
        if not child.meta.parent:
            return
        supervisor = read_doc(child.meta.parent, root=root)
        if not any(
            blocker.child_id == child.meta.id
            and blocker.incident_id == reservation.reservation_id
            for blocker in supervisor.meta.monitoring_blockers
        ):
            return
        from cascade.watchdog.blockage import reconcile_direct_report_blockage

        reconcile_direct_report_blockage(
            supervisor,
            child,
            root=root,
            incident_id=reservation.reservation_id,
        )
    except Exception:
        # Result persistence is authoritative. A concurrent board change leaves
        # the exact blocker for the next reconciliation pass.
        _log.exception(
            "could not reconcile audit blocker %s", reservation.reservation_id
        )


__all__ = ["AuditRecoveryWorker", "dispatch_audit_recovery"]
