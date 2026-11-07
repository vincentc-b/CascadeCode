"""Human-authorized lifecycle command for active provider recovery.

The recovery engine owns the all-or-nothing document/checkpoint update.  This
module owns the boundary around it: close admission for the active item, wait
for an admitted turn to leave, and only then hand the selected disposition to
the normal kickoff path.  In particular, a fresh recovery never resumes the
old provider's pending graph edge.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal

from cascade.agent.discovery.inventory import (
    ProviderInventoryResult,
    refresh_provider_inventory,
)
from cascade.agent.execution_preflight import provider_blocker
from cascade.agent.flex_continuation import (
    FlexContinuationEligibility,
    evaluate_flex_continuation_eligibility,
)
from cascade.agent.selection_preflight import evaluate_work_selection
from cascade.board.context import resolve_root
from cascade.board.errors import BoardError, NotFound
from cascade.workspace.doc_root import read_doc_resolved
from cascade.epic.lifecycle_gate import LifecycleGate, lifecycle_gate
from cascade.provider_recovery import (
    ProviderRecoveryRequest,
    ProviderRecoveryResult,
    recover_active_item_provider,
)
from cascade.watchdog.lock import process_lock
from cascade.workspace.types import KickoffReason

Actor = Literal[
    "human", "agent", "system", "scheduler", "refresh", "automatic_retry"
]
Kickoff = Callable[[KickoffReason], None]


@dataclass(frozen=True, slots=True)
class ProviderRecoveryCommandResult:
    """A stable, non-secret response for the human recovery control."""

    ok: bool
    work_id: str
    disposition: str | None = None
    reason: str | None = None
    error_code: str | None = None
    idempotent: bool = False

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        return {key: value for key, value in result.items() if value is not None}


def continue_without_flex_eligibility(
    work_id: str,
    *,
    root: Path | None = None,
    inventory: ProviderInventoryResult | None = None,
    lifecycle_eligible: bool = True,
    approval_eligible: bool = True,
) -> FlexContinuationEligibility:
    """Compute a fresh action-bound projection without authorizing anything."""

    repo = resolve_root(root)
    blocker = provider_blocker(work_id, root=repo)
    failed_action = blocker.get("failed_action") if blocker else None
    failed_preflight = blocker.get("failed_preflight") if blocker else None
    if not isinstance(failed_action, dict) or not isinstance(failed_preflight, dict):
        return evaluate_flex_continuation_eligibility(
            failed_action=failed_action if isinstance(failed_action, dict) else None,
            failed_preflight=(
                failed_preflight if isinstance(failed_preflight, dict) else None
            ),
            disabled_preflight=None,
        )
    preliminary = evaluate_flex_continuation_eligibility(
        failed_action=failed_action,
        failed_preflight=failed_preflight,
        disabled_preflight=None,
        lifecycle_eligible=lifecycle_eligible,
        approval_eligible=approval_eligible,
    )
    if preliminary.reason_code != "inventory_not_fresh":
        return preliminary
    try:
        doc = read_doc_resolved(work_id, root=repo)
        current = evaluate_work_selection(
            doc,
            root=repo,
            inventory=inventory or refresh_provider_inventory(),
            action=str(failed_action.get("action_kind") or "continuation"),
            disable_flex=True,
        ).result
    except (BoardError, OSError, ValueError):
        current = None
    return evaluate_flex_continuation_eligibility(
        failed_action=failed_action,
        failed_preflight=failed_preflight,
        disabled_preflight=current,
        lifecycle_eligible=lifecycle_eligible,
        approval_eligible=approval_eligible,
    )


def continue_without_flex_eligibility_command(
    work_id: str,
    *,
    actor: Actor = "system",
    root: Path | None = None,
    inventory: ProviderInventoryResult | None = None,
    lifecycle_eligible: bool = True,
    approval_eligible: bool = True,
) -> FlexContinuationEligibility:
    """Human-only command boundary used by the eventual authorization route.

    This task remains read-only: a successful response says that a later
    authorization command may proceed, not that a waiver has been created.
    """

    if actor != "human":
        return FlexContinuationEligibility(
            False,
            "unauthorized",
            "An explicit human authorization is required.",
            work_id=work_id or None,
        )
    return continue_without_flex_eligibility(
        work_id,
        root=root,
        inventory=inventory,
        lifecycle_eligible=lifecycle_eligible,
        approval_eligible=approval_eligible,
    )


def recover_active_item_provider_command(
    work_id: str,
    request: ProviderRecoveryRequest,
    *,
    actor: Actor = "system",
    root: Path | None = None,
    inventory: ProviderInventoryResult | None = None,
    gate: LifecycleGate | None = None,
    quiesce_timeout: float = 0.0,
    kickoff: Kickoff | None = None,
) -> ProviderRecoveryCommandResult:
    """Apply one human-selected provider replacement to an active work item.

    Successful selections are recorded before the turn is handed off, so a
    repeated click with the same selection cannot create a second role turn.
    The record is intentionally scoped to the exact selection; a later human
    choice is a separate recovery request.
    """

    if actor != "human":
        return _error(work_id, "unauthorized", "A human authorization is required.")
    if not isinstance(work_id, str) or not work_id.strip():
        return _error("", "invalid_work_id", "An active work item ID is required.")
    if not isinstance(request, ProviderRecoveryRequest):
        return _error(work_id, "invalid_request", "A complete provider selection is required.")

    repo = resolve_root(root)
    try:
        with process_lock:
            doc = read_doc_resolved(work_id, root=repo)
            if doc.meta.tier not in ("epic", "feature", "task") or not _is_active(doc):
                return _error(work_id, "not_active", "Provider recovery is only available for active work.")
            epic_id = _owning_epic(doc.meta.id, doc.meta.tier, doc.meta.parent, repo)
            fingerprint = _request_fingerprint(request)
            previous = _read_completed(repo, work_id, fingerprint)
            if previous is not None:
                return ProviderRecoveryCommandResult(
                    True,
                    work_id,
                    disposition=previous["disposition"],
                    reason=previous["reason"],
                    idempotent=True,
                )
    except (BoardError, OSError, ValueError):
        return _error(work_id, "unavailable", "The active work item could not be read safely.")

    handoff: KickoffReason | None = None
    with (gate or lifecycle_gate()).transition(
        # The gate's lock is keyed by the owning Epic.  Include it as the
        # anchor while also closing admission for the item whose pins change.
        epic_id, tuple(dict.fromkeys((epic_id, work_id))), timeout=quiesce_timeout
    ) as quiesced:
        if not quiesced:
            return _error(work_id, "lifecycle_busy", "The active turn did not quiesce; no selection was changed.")
        try:
            with process_lock:
                # Re-read identity and active state after closing admission.
                doc = read_doc_resolved(work_id, root=repo)
                if doc.meta.tier not in ("epic", "feature", "task") or not _is_active(doc):
                    return _error(work_id, "not_active", "Provider recovery is only available for active work.")
                if _owning_epic(doc.meta.id, doc.meta.tier, doc.meta.parent, repo) != epic_id:
                    return _error(work_id, "lifecycle_changed", "The work hierarchy changed; retry from the refreshed board.")
                fingerprint = _request_fingerprint(request)
                previous = _read_completed(repo, work_id, fingerprint)
                if previous is not None:
                    return ProviderRecoveryCommandResult(
                        True, work_id, previous["disposition"], previous["reason"], idempotent=True
                    )

                recovered = recover_active_item_provider(
                    work_id, request, root=repo, inventory=inventory
                )
                if recovered.disposition in ("validation_failed", "rolled_back"):
                    return _engine_failure(recovered)

                if recovered.disposition == "fresh_role_turn":
                    _reconstruct_role_turn(work_id, doc.meta.tier, doc.meta.parent, repo)
                elif recovered.disposition != "resume_compatible":
                    return _error(work_id, "recovery_failed", "Provider recovery returned an unknown disposition.")

                _write_completed(repo, work_id, fingerprint, recovered)
                handoff = KickoffReason(
                    kind="resume_inflight",
                    work_id=work_id,
                    by="human",
                    root=repo,
                    feature_id=doc.meta.parent if doc.meta.tier == "task" else None,
                )
        except (BoardError, OSError, ValueError, NotFound):
            return _error(work_id, "recovery_failed", "Provider recovery could not complete safely.")

    # Lifecycle admission is open again.  Starting inside the transition would
    # reject our own kickoff and would risk lock inversion with graph storage.
    if handoff is not None:
        (kickoff or _kickoff)(handoff)
    return ProviderRecoveryCommandResult(
        True, work_id, recovered.disposition, recovered.reason  # type: ignore[union-attr]
    )


def recover_active_provider(*args, **kwargs) -> ProviderRecoveryCommandResult:
    """Short public alias kept convenient for API and tool adapters."""

    return recover_active_item_provider_command(*args, **kwargs)


def _is_active(doc) -> bool:
    return doc.meta.status == "active" and doc.meta.path.parent.name == "2_active"


def _owning_epic(work_id: str, tier: str, parent: str | None, root: Path) -> str:
    if tier == "epic":
        return work_id
    if not parent:
        raise ValueError("non-epic work has no parent")
    parent_doc = read_doc_resolved(parent, root=root)
    if parent_doc.meta.tier == "epic":
        return parent_doc.meta.id
    if parent_doc.meta.tier != "feature" or not parent_doc.meta.parent:
        raise ValueError("work hierarchy is invalid")
    epic = read_doc_resolved(parent_doc.meta.parent, root=root)
    if epic.meta.tier != "epic":
        raise ValueError("work hierarchy has no epic")
    return epic.meta.id


def _reconstruct_role_turn(work_id: str, tier: str, parent: str | None, root: Path) -> None:
    """Replace a pending provider-specific edge with a safe new role edge."""

    message = {
        "role": "event",
        "name": "ProviderRecoveryRequested",
        "content": "Provider selection recovered by a human; continue from preserved work.",
    }
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph, config = ensure_epic_graph(work_id, root=root), thread_config(work_id)
    elif tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph, config = ensure_feature_graph(work_id, root=root), thread_config(work_id)
    else:
        from cascade.task.checkpoint import thread_config
        from cascade.task.graph import ensure_task_graph

        graph, config = ensure_task_graph(work_id, root=root, feature_id=parent), thread_config(work_id)
    # Naming ``ingest`` makes LangGraph continue at the first role node rather
    # than resuming the pending opaque provider invocation.  Existing messages
    # (plan/progress/worktree context) and selection pins remain in the state.
    graph.update_state(config, {"messages": [message]}, as_node="ingest")


def _request_fingerprint(request: ProviderRecoveryRequest) -> str:
    payload = {
        "provider": request.provider,
        "models": dict(sorted(request.models.items())),
        "reasoning": dict(sorted((request.reasoning or {}).items())),
        "flex_mode": request.flex_mode,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ledger_path(root: Path) -> Path:
    return root / ".cascade" / "provider_recoveries.json"


def _read_completed(root: Path, work_id: str, fingerprint: str) -> dict[str, str] | None:
    path = _ledger_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return None
    row = payload.get("recoveries", {}).get(f"{work_id}:{fingerprint}") if isinstance(payload, dict) else None
    if not isinstance(row, dict):
        return None
    disposition, reason = row.get("disposition"), row.get("reason")
    if not isinstance(disposition, str) or not isinstance(reason, str):
        return None
    return {"disposition": disposition, "reason": reason}


def _write_completed(root: Path, work_id: str, fingerprint: str, result: ProviderRecoveryResult) -> None:
    path = _ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, object] = {}
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        existing = {}
    rows = dict(existing.get("recoveries") or {}) if isinstance(existing, dict) else {}
    rows[f"{work_id}:{fingerprint}"] = {"disposition": result.disposition, "reason": result.reason}
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            # Flex continuation waivers and descendant stamps share this
            # ledger.  Provider replacement must preserve those independent
            # rows instead of rebuilding the file around legacy recoveries.
            payload = dict(existing) if isinstance(existing, dict) else {}
            payload.update({"version": 2, "recoveries": rows})
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def _engine_failure(result: ProviderRecoveryResult) -> ProviderRecoveryCommandResult:
    code = "selection_invalid" if result.disposition == "validation_failed" else "persistence_failed"
    return _error(result.work_id, code, result.reason, disposition=result.disposition)


def _error(
    work_id: str, code: str, reason: str, *, disposition: str | None = None
) -> ProviderRecoveryCommandResult:
    return ProviderRecoveryCommandResult(False, work_id, disposition, reason, code)


def _kickoff(reason: KickoffReason) -> None:
    from cascade.workspace.kickoff import kickoff_turn

    kickoff_turn(reason)


__all__ = [
    "ProviderRecoveryCommandResult",
    "recover_active_item_provider_command",
    "recover_active_provider",
]
