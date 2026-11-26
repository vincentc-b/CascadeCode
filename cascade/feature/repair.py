"""Generation-bound admission of late work to an existing Feature.

The repair receipt is deliberately stored in the existing action ledger.  A
queue event by itself is not authority: the watchdog joins it to this receipt
and to the exact active document bytes before allowing the introduction.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from cascade.board.errors import GitError
from cascade.board.gitutil import head_sha, last_commit_touching, read_blob
from cascade.board.parse import parse_doc, render_doc
from cascade.board.store import save_doc
from cascade.comments.gate import blocking_threads_for, refusal_if_blocked
from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.feature.registry import register_feature_tool
from cascade.task.action_recovery import (
    ActionRecoveryUnavailable,
    _actions,
    _read_payload,
    _write_payload,
)
from cascade.task.execution import execution_lease_is_live
from cascade.task.lifecycle_lock import (
    lifecycle_root,
    task_lifecycle_lock,
    task_lifecycle_read_lock,
)
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import (
    git_root_for_path,
    integration_branch,
    merged_board,
    resolve_mutation_owner,
)

RepairOperation = Literal["inspect", "admit", "resume"]
_ACTIVE_PHASES = frozenset(
    {
        "prepared",
        "authority_recorded",
        "parent_enabled",
        "delivery_pending",
        "review_pending",
        "integration_pending",
        "retirement_pending",
    }
)
_MARKER_PREFIX = "<!-- cascade-feature-repair:"
_OPEN_REVIEW_REQUIRED_FIELDS = (
    "reason",
    "approval_reference",
    "scope_reference",
    "review_url",
    "review_forge",
    "source_ref",
    "target_ref",
    "observed_source_head",
    "observed_target_head",
    "observed_review_generation",
)


class FeatureRepairError(ValueError):
    """The exact Feature repair cannot be admitted or resumed."""


class _FeatureRepairRefusal(FeatureRepairError):
    """Internal typed prerequisite result for open-review admission."""

    def __init__(self, code: str, next_prerequisite: str, *, terminal: bool = False):
        super().__init__(code)
        self.code = code
        self.next_prerequisite = next_prerequisite
        self.terminal = terminal


def _digest(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _stable_action_id(feature_id: str, request_id: str) -> str:
    value = _digest(f"feature_repair\0{feature_id}\0{request_id}")[:24]
    return f"feature_repair:{feature_id}:{value}"


def _copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value)))


def _result(action: Mapping[str, Any], *, replayed: bool = False) -> dict[str, Any]:
    phase = str(action.get("phase", ""))
    admitted = phase in _ACTIVE_PHASES
    verified = phase == "verified"
    return {
        "ok": admitted or verified,
        "action_id": action.get("action_id"),
        "generation": action.get("generation"),
        "phase": action.get("phase"),
        "blocker": action.get("blocker"),
        "next_action": action.get("next_action"),
        "evidence": {
            "authority_event_id": action.get("authority_event_id"),
            "introduction_commit": action.get("introduction_commit"),
            "introduction_blob": action.get("introduction_blob"),
        },
        "replayed": replayed,
        "requested": True,
        "admitted": admitted,
        "acknowledged": True,
        "executing": phase in {"delivery_pending", "review_pending", "integration_pending"},
        "executed": phase in {"retirement_pending", "verified"},
        "waiting": phase == "waiting",
        "refused": phase == "refused",
        "verification_pending": admitted and not verified,
        "verified": verified,
        "next_prerequisite": action.get("next_action"),
    }


def _typed_refusal(
    action_id: str,
    refusal: _FeatureRepairRefusal,
    *,
    action: Mapping[str, Any] | None = None,
    replayed: bool = False,
) -> dict[str, Any]:
    phase = "refused" if refusal.terminal else "waiting"
    generation = action.get("generation") if action is not None else None
    return {
        "ok": False,
        "action_id": action_id,
        "generation": generation,
        "phase": phase,
        "blocker": refusal.code,
        "next_action": refusal.next_prerequisite,
        "next_prerequisite": refusal.next_prerequisite,
        "evidence": {},
        "replayed": replayed,
        "requested": True,
        "admitted": False,
        "acknowledged": action is not None,
        "executing": False,
        "executed": False,
        "waiting": not refusal.terminal,
        "refused": refusal.terminal,
        "verification_pending": False,
        "verified": False,
    }


def inspect_feature_repair(
    feature_id: str,
    request_id: str,
    *,
    root: Path,
) -> dict[str, Any]:
    """Inspect one stable request without creating lifecycle state."""

    repo = lifecycle_root(Path(root).resolve())
    action_id = _stable_action_id(feature_id, request_id)
    with task_lifecycle_read_lock(root=repo):
        action = _actions(_read_payload(repo)).get(action_id)
    if action is None:
        return {
            "ok": False,
            "action_id": action_id,
            "generation": None,
            "phase": "absent",
            "blocker": "repair_not_prepared",
            "next_action": "admit",
            "evidence": {},
            "replayed": False,
        }
    return _result(action, replayed=True)


def inspect_open_review_repair(
    feature_id: str,
    request_id: str,
    *,
    root: Path,
    reason: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    requesting_parent_id: str | None = None,
    authenticated_human: AuthenticatedHuman | None = None,
    approval_reference: str | None = None,
    scope_reference: str | None = None,
    review_url: str | None = None,
    review_forge: str | None = None,
    source_ref: str | None = None,
    target_ref: str | None = None,
    observed_source_head: str | None = None,
    observed_target_head: str | None = None,
    observed_review_generation: int | None = None,
    claim_id: str | None = None,
    incident_budget_id: str | None = None,
) -> dict[str, Any]:
    """Inspect an open-review replay and enforce its canonical fingerprint."""

    try:
        request = _open_review_request(
            reason=reason,
            evidence=evidence,
            requesting_parent_id=requesting_parent_id,
            authenticated_human=authenticated_human,
            approval_reference=approval_reference,
            scope_reference=scope_reference,
            review_url=review_url,
            review_forge=review_forge,
            source_ref=source_ref,
            target_ref=target_ref,
            observed_source_head=observed_source_head,
            observed_target_head=observed_target_head,
            observed_review_generation=observed_review_generation,
            claim_id=claim_id,
            incident_budget_id=incident_budget_id,
        )
    except FeatureRepairError as exc:
        code = str(exc).replace(" ", "_")
        return _typed_refusal(
            _stable_action_id(feature_id, request_id),
            _FeatureRepairRefusal(code, "complete_repair_request"),
        )
    if request is None:  # pragma: no cover - the wrapper requires open-review fields
        raise FeatureRepairError("open review repair request content is required")

    repo = lifecycle_root(Path(root).resolve())
    action_id = _stable_action_id(feature_id, request_id)
    with task_lifecycle_read_lock(root=repo):
        action = _actions(_read_payload(repo)).get(action_id)
    if action is None:
        return inspect_feature_repair(feature_id, request_id, root=repo)
    if action.get("request_digest") != _request_digest(request):
        return _typed_refusal(
            action_id,
            _FeatureRepairRefusal(
                "request_content_changed",
                "submit_a_new_request_id",
                terminal=True,
            ),
            action=action,
            replayed=True,
        )
    return _result(action, replayed=True)


def feature_repair(
    feature_id: str,
    request_id: str,
    *,
    root: Path,
    operation: RepairOperation = "inspect",
    task_id: str | None = None,
    approval_reference: str | None = None,
    scope_reference: str | None = None,
    expected_generation: int | None = None,
    claim_owner: str | None = None,
    reason: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    requesting_parent_id: str | None = None,
    authenticated_human: AuthenticatedHuman | None = None,
    review_url: str | None = None,
    review_forge: str | None = None,
    source_ref: str | None = None,
    target_ref: str | None = None,
    observed_source_head: str | None = None,
    observed_target_head: str | None = None,
    observed_review_generation: int | None = None,
    claim_id: str | None = None,
    incident_budget_id: str | None = None,
) -> dict[str, Any]:
    """Inspect, admit, or resume an exact generation-bound Feature repair.

    ``request_id`` is the queued Task delivery action (or reserved mint request)
    identity.  It, rather than a caller-selected role, supplies replay identity.
    """

    if operation == "inspect":
        return inspect_feature_repair(feature_id, request_id, root=root)
    if operation not in {"admit", "resume"}:
        raise FeatureRepairError(f"unknown feature repair operation: {operation}")
    open_request = _open_review_request(
        reason=reason,
        evidence=evidence,
        requesting_parent_id=requesting_parent_id,
        authenticated_human=authenticated_human,
        approval_reference=approval_reference,
        scope_reference=scope_reference,
        review_url=review_url,
        review_forge=review_forge,
        source_ref=source_ref,
        target_ref=target_ref,
        observed_source_head=observed_source_head,
        observed_target_head=observed_target_head,
        observed_review_generation=observed_review_generation,
        claim_id=claim_id,
        incident_budget_id=incident_budget_id,
    )
    return _admit_or_resume(
        feature_id,
        request_id,
        root=Path(root).resolve(),
        task_id=task_id,
        approval_reference=approval_reference,
        scope_reference=scope_reference,
        expected_generation=expected_generation,
        claim_owner=claim_owner,
        resume=operation == "resume",
        open_request=open_request,
    )


def admit_feature_repair(
    feature_id: str, request_id: str, *, root: Path, **kwargs: Any
) -> dict[str, Any]:
    return feature_repair(
        feature_id, request_id, root=root, operation="admit", **kwargs
    )


def resume_feature_repair(
    feature_id: str, request_id: str, *, root: Path, **kwargs: Any
) -> dict[str, Any]:
    return feature_repair(
        feature_id, request_id, root=root, operation="resume", **kwargs
    )


def admit_open_review_repair(
    feature_id: str, request_id: str, *, root: Path, **kwargs: Any
) -> dict[str, Any]:
    """Admit one scoped request against the Feature's existing open review.

    The caller supplies the review observation it is acting on.  Admission
    joins that evidence to the current local review registry while holding the
    lifecycle fence; stale or incomplete evidence is returned as a typed
    prerequisite rather than being converted into a new review or Task
    mismatch.
    """

    try:
        return feature_repair(
            feature_id, request_id, root=root, operation="admit", **kwargs
        )
    except FeatureRepairError as exc:
        code = str(exc).replace(" ", "_")
        return _typed_refusal(
            _stable_action_id(feature_id, request_id),
            _FeatureRepairRefusal(code, "complete_repair_request"),
        )


def repair_action_for_mint(
    feature_id: str, request_id: str, *, root: Path
) -> dict[str, Any]:
    """Return the admitted mint action bound to the current Feature generation.

    Callers hold ``task_lifecycle_lock``.  This deliberately reads the action
    ledger without acquiring a review-registry lock, preserving the lifecycle
    lock ordering used by mint and closeout.
    """

    action_id = _stable_action_id(feature_id, request_id)
    action = _actions(_read_payload(lifecycle_root(root))).get(action_id)
    if (
        action is None
        or action.get("kind") != "feature_repair"
        or action.get("feature_id") != feature_id
        or action.get("task_id") is not None
        or action.get("phase") not in _ACTIVE_PHASES
    ):
        raise FeatureRepairError("mint requires an admitted feature repair action")
    marker = (
        f"{_MARKER_PREFIX} action_id={action_id} "
        f"generation={action.get('generation')} -->"
    )
    doc, _ = _current_feature(feature_id, lifecycle_root(root))
    if doc.meta.status != "active" or marker not in doc.body:
        raise FeatureRepairError("mint repair generation is not the current Feature")
    return action


def reserve_repair_child(
    action_id: str,
    *,
    task_id: str,
    spec_digest: str,
    request_digest: str,
    root: Path,
) -> dict[str, Any]:
    """Persist one child identity and exact spec before either parent write.

    Replaying the same action returns the same reservation.  A changed title,
    dependency set, backend selection, or other rendered-spec field changes the
    digest and therefore fails closed instead of allocating another Task.
    """

    repo = lifecycle_root(root)
    payload = _read_payload(repo)
    actions = _actions(payload)
    action = actions.get(action_id)
    if action is None or action.get("kind") != "feature_repair":
        raise FeatureRepairError(
            "feature repair action disappeared before child reserve"
        )
    existing_id = action.get("reserved_task_id")
    existing_digest = action.get("reserved_task_spec_digest")
    if existing_id is not None or existing_digest is not None:
        if (
            existing_id != task_id
            or existing_digest != spec_digest
            or action.get("reserved_mint_request_digest") != request_digest
        ):
            raise FeatureRepairError("reserved repair child specification changed")
        return action
    action.update(
        reserved_task_id=task_id,
        reserved_task_spec_digest=spec_digest,
        reserved_mint_request_digest=request_digest,
        phase="delivery_pending",
        next_action="persist_reserved_task",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    actions[action_id] = action
    payload["actions"] = actions
    _write_payload(repo, payload)
    return action


def mark_repair_child_persisted(action_id: str, *, root: Path) -> None:
    """Checkpoint both idempotent child writes after canonical readback."""

    repo = lifecycle_root(root)
    payload = _read_payload(repo)
    actions = _actions(payload)
    action = actions.get(action_id)
    if action is None or action.get("kind") != "feature_repair":
        raise FeatureRepairError("feature repair action disappeared after child write")
    action.update(
        child_persisted=True,
        phase="delivery_pending",
        next_action="deliver_reserved_task",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    actions[action_id] = action
    payload["actions"] = actions
    _write_payload(repo, payload)


def current_feature_repair_generation(feature_id: str, *, root: Path) -> int:
    """Return the greatest live repair generation, or zero for ordinary work."""

    try:
        actions = _actions(_read_payload(lifecycle_root(root)))
    except ActionRecoveryUnavailable:
        return 0
    return max(
        (
            int(action.get("generation") or 0)
            for action in actions.values()
            if action.get("kind") == "feature_repair"
            and action.get("feature_id") == feature_id
            and action.get("phase") in _ACTIVE_PHASES
        ),
        default=0,
    )


def current_feature_repair_record(
    feature_id: str, *, root: Path
) -> dict[str, Any] | None:
    """Return a copy of the greatest live repair action for review binding."""

    try:
        actions = _actions(_read_payload(lifecycle_root(root)))
    except ActionRecoveryUnavailable:
        return None
    candidates = [
        action
        for action in actions.values()
        if action.get("kind") == "feature_repair"
        and action.get("feature_id") == feature_id
        and action.get("phase") in _ACTIVE_PHASES
    ]
    if not candidates:
        return None
    return _copy(max(candidates, key=lambda row: int(row.get("generation") or 0)))


def feature_repair_actions(feature_id: str, *, root: Path) -> list[dict[str, Any]]:
    """Project all generations for closeout while the lifecycle fence is held."""

    try:
        actions = _actions(_read_payload(lifecycle_root(root)))
    except ActionRecoveryUnavailable:
        return []
    return [
        _copy(action)
        for action in actions.values()
        if action.get("kind") == "feature_repair"
        and action.get("feature_id") == feature_id
    ]


def mark_feature_repair_verified(
    feature_id: str, generation: int, *, root: Path
) -> None:
    """Make a satisfied generation historical before checkout retirement."""

    repo = lifecycle_root(root)
    payload = _read_payload(repo)
    actions = _actions(payload)
    changed = False
    for action_id, action in actions.items():
        if (
            action.get("kind") == "feature_repair"
            and action.get("feature_id") == feature_id
            and int(action.get("generation") or 0) == generation
        ):
            action.update(
                phase="verified",
                next_action=None,
                verified_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            actions[action_id] = action
            changed = True
            break
    if changed:
        payload["actions"] = actions
        _write_payload(repo, payload)


def mark_feature_repair_delivery_pending(
    task_id: str, delivery_evidence: Mapping[str, str], *, root: Path
) -> None:
    """Bind a green Task pair to the live repair without changing its identity."""

    repo = lifecycle_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        actions = _actions(payload)
        candidates = [
            (action_id, action)
            for action_id, action in actions.items()
            if action.get("kind") == "feature_repair"
            and action.get("phase") in _ACTIVE_PHASES
            and (
                action.get("task_id") == task_id
                or action.get("reserved_task_id") == task_id
                or action.get("request_id") == f"{task_id}:queued_merge"
            )
        ]
        if not candidates:
            return
        action_id, action = max(
            candidates, key=lambda row: int(row[1].get("generation") or 0)
        )
        if action.get("phase") in {"prepared", "authority_recorded"}:
            raise FeatureRepairError(
                "Task validation cannot precede repair parent introduction"
            )
        action.update(
            phase="delivery_pending",
            final_validation=dict(delivery_evidence),
            next_action="merge_original_task_delivery",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        actions[action_id] = action
        payload["actions"] = actions
        _write_payload(repo, payload)


def _open_review_request(
    *,
    reason: str | None,
    evidence: Mapping[str, Any] | None,
    requesting_parent_id: str | None,
    authenticated_human: AuthenticatedHuman | None,
    approval_reference: str | None,
    scope_reference: str | None,
    review_url: str | None,
    review_forge: str | None,
    source_ref: str | None,
    target_ref: str | None,
    observed_source_head: str | None,
    observed_target_head: str | None,
    observed_review_generation: int | None,
    claim_id: str | None,
    incident_budget_id: str | None,
) -> dict[str, Any] | None:
    if authenticated_human is not None and not isinstance(
        authenticated_human, AuthenticatedHuman
    ):
        raise FeatureRepairError(
            "authenticated_human must come from an authenticated boundary"
        )
    values: dict[str, Any] = {
        "reason": reason,
        "evidence": dict(evidence) if isinstance(evidence, Mapping) else evidence,
        "requesting_parent_id": requesting_parent_id,
        "authenticated_human": authenticated_human.subject
        if isinstance(authenticated_human, AuthenticatedHuman)
        else authenticated_human,
        "approval_reference": approval_reference,
        "scope_reference": scope_reference,
        "review_url": review_url,
        "review_forge": review_forge,
        "source_ref": source_ref,
        "target_ref": target_ref,
        "observed_source_head": observed_source_head,
        "observed_target_head": observed_target_head,
        "observed_review_generation": observed_review_generation,
        "claim_id": claim_id,
        "incident_budget_id": incident_budget_id,
    }
    open_only_fields = (
        reason,
        evidence,
        requesting_parent_id,
        authenticated_human,
        review_url,
        review_forge,
        source_ref,
        target_ref,
        observed_source_head,
        observed_target_head,
        observed_review_generation,
        claim_id,
        incident_budget_id,
    )
    if not any(value is not None for value in open_only_fields):
        return None
    if evidence is None or not isinstance(evidence, Mapping):
        raise FeatureRepairError("open review repair evidence must be a mapping")
    try:
        normalized = json.loads(json.dumps(values, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise FeatureRepairError("open review repair evidence must be JSON-safe") from exc
    missing = [
        field
        for field in _OPEN_REVIEW_REQUIRED_FIELDS
        if normalized.get(field) in {None, ""}
    ]
    if missing:
        raise FeatureRepairError(
            f"open review repair request is missing {', '.join(missing)}"
        )
    for field in (
        "reason",
        "approval_reference",
        "scope_reference",
        "review_url",
        "review_forge",
        "source_ref",
        "target_ref",
        "observed_source_head",
        "observed_target_head",
    ):
        value = normalized[field]
        if not isinstance(value, str) or not value.strip():
            raise FeatureRepairError(f"open review repair {field} must be nonempty")
    if bool(requesting_parent_id) == bool(authenticated_human):
        raise FeatureRepairError(
            "open review repair requires exactly one parent or authenticated human authority"
        )
    if isinstance(observed_review_generation, bool) or not isinstance(
        observed_review_generation, int
    ) or observed_review_generation < 0:
        raise FeatureRepairError("observed review generation must be nonnegative")
    normalized["authority"] = (
        {"kind": "parent", "id": requesting_parent_id}
        if requesting_parent_id
        else {"kind": "authenticated_human", "id": authenticated_human.subject}
    )
    normalized.pop("requesting_parent_id", None)
    normalized.pop("authenticated_human", None)
    return normalized


def _request_digest(request: Mapping[str, Any]) -> str:
    return _digest(
        json.dumps(dict(request), sort_keys=True, separators=(",", ":"))
    )


def _admit_or_resume(
    feature_id: str,
    request_id: str,
    *,
    root: Path,
    task_id: str | None,
    approval_reference: str | None,
    scope_reference: str | None,
    expected_generation: int | None,
    claim_owner: str | None,
    resume: bool,
    open_request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not feature_id.startswith("feat_") or not request_id.strip():
        raise FeatureRepairError(
            "feature_id and request_id must be stable nonempty identities"
        )
    action_id = _stable_action_id(feature_id, request_id)
    content_digest = _request_digest(open_request) if open_request is not None else None
    repo = lifecycle_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        actions = _actions(payload)
        existing = actions.get(action_id)
        if existing is not None:
            if open_request is not None:
                stored_digest = existing.get("request_digest")
                if stored_digest != content_digest:
                    return _typed_refusal(
                        action_id,
                        _FeatureRepairRefusal(
                            "request_content_changed",
                            "submit_a_new_request_id",
                            terminal=True,
                        ),
                        action=existing,
                        replayed=True,
                    )
            elif existing.get("request_digest") is not None:
                raise FeatureRepairError(
                    "open review repair requires its original request content"
                )
            if (
                expected_generation is not None
                and existing.get("generation") != expected_generation
            ):
                raise FeatureRepairError("stale feature repair generation")
            for field, current in (
                ("task_id", task_id),
                ("approval_reference", approval_reference),
                ("scope_reference", scope_reference),
            ):
                if current is not None and existing.get(field) != current:
                    raise FeatureRepairError(f"feature repair {field} changed")
            if claim_owner is not None and existing.get("claim_owner") not in {
                None,
                claim_owner,
            }:
                raise FeatureRepairError(
                    "feature repair claim is owned by another caller"
                )
            action = existing
        else:
            if resume:
                raise FeatureRepairError("feature repair has not been admitted")
            if open_request is not None:
                current = [
                    row
                    for row in actions.values()
                    if row.get("kind") == "feature_repair"
                    and row.get("feature_id") == feature_id
                    and row.get("phase") in _ACTIVE_PHASES
                ]
                if current:
                    writer = max(
                        current, key=lambda row: int(row.get("generation") or 0)
                    )
                    return _typed_refusal(
                        str(writer.get("action_id") or action_id),
                        _FeatureRepairRefusal(
                            "repair_writer_active", "join_current_repair_generation"
                        ),
                        action=writer,
                        replayed=True,
                    )
            generation = 1 + max(
                (
                    int(row.get("generation") or 0)
                    for row in actions.values()
                    if row.get("kind") == "feature_repair"
                    and row.get("feature_id") == feature_id
                ),
                default=0,
            )
            if expected_generation not in {None, generation}:
                raise FeatureRepairError("stale feature repair generation")
            action = (
                _prepare_open_review_action(
                    feature_id,
                    request_id,
                    action_id=action_id,
                    generation=generation,
                    request=open_request,
                    claim_owner=claim_owner,
                    root=repo,
                )
                if open_request is not None
                else _prepare_action(
                    feature_id,
                    request_id,
                    action_id=action_id,
                    generation=generation,
                    task_id=task_id,
                    approval_reference=approval_reference,
                    scope_reference=scope_reference,
                    claim_owner=claim_owner,
                    root=repo,
                )
            )
            actions[action_id] = action
            payload["version"] = max(int(payload.get("version") or 1), 3)
            payload["actions"] = actions
            _write_payload(repo, payload)

        if existing is not None and action.get("phase") in {
            "prepared",
            "authority_recorded",
            "waiting",
        }:
            if action.get("phase") == "waiting":
                action.update(phase="prepared", blocker=None)
            attempts = list(action.get("attempts") or [])
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "resumed_at": datetime.now(timezone.utc).isoformat(),
                    "outcome": None,
                }
            )
            action["attempts"] = attempts
            actions[action_id] = action
            payload["actions"] = actions
            _write_payload(repo, payload)

        # Re-read every mutable gate while holding the lifecycle lock.  A
        # prepared receipt is not permission to ignore a later lease or owner.
        doc, owner_root = _current_feature(feature_id, repo)
        try:
            _recheck_action(
                action, doc, owner_root=owner_root, task_id=task_id, root=repo
            )
        except _FeatureRepairRefusal as refusal:
            action.update(
                phase="refused" if refusal.terminal else "waiting",
                blocker=refusal.code,
                next_action=refusal.next_prerequisite,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            actions[action_id] = action
            payload["actions"] = actions
            _write_payload(repo, payload)
            return _typed_refusal(
                action_id, refusal, action=action, replayed=existing is not None
            )
        except FeatureRepairError as exc:
            if open_request is None:
                raise
            code = str(exc).replace(" ", "_")
            refusal = _FeatureRepairRefusal(code, "refresh_repair_prerequisites")
            action.update(
                phase="waiting",
                blocker=refusal.code,
                next_action=refusal.next_prerequisite,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            actions[action_id] = action
            payload["actions"] = actions
            _write_payload(repo, payload)
            return _typed_refusal(
                action_id, refusal, action=action, replayed=existing is not None
            )
        if action.get("phase") not in {"prepared", "authority_recorded"}:
            return _result(action, replayed=True)
        event_id = str(
            action.get("authority_event_id") or f"{action_id}:g{action['generation']}"
        )
        if action.get("phase") == "prepared":
            event = Event(
                type="FeatureRepairAuthorized",
                ts=datetime.now(timezone.utc),
                payload={
                    "id": feature_id,
                    "feature_id": feature_id,
                    "epic_id": action["epic_id"],
                    "action_id": action_id,
                    "generation": action["generation"],
                    "event_id": event_id,
                    "owner_fingerprint": action["owner_fingerprint"],
                    "source_ref": action["source_ref"],
                    "target_ref": action["target_ref"],
                    "source_head": action.get("source_head"),
                    "target_head": action.get("target_head"),
                    "request_digest": action.get("request_digest"),
                    "review_url": action.get("review_url"),
                    "review_generation": action.get("review_generation"),
                    "claim_id": action.get("claim_id"),
                    "incident_budget_id": action.get("incident_budget_id"),
                    "intended_active_path": action["intended_active_path"],
                    "document_digest": action["intended_document_digest"],
                },
                dest=feature_id,
            )
            queued, _ = read_events(feature_id, 0, root=repo)
            if not any(
                row.type == "FeatureRepairAuthorized"
                and row.payload.get("event_id") == event_id
                for row in queued
            ):
                append_event(
                    feature_id,
                    event,
                    root=repo,
                )
            action.update(
                phase="authority_recorded",
                authority_event_id=event_id,
                authority_recorded_at=datetime.now(timezone.utc).isoformat(),
                next_action="introduce_exact_active_document",
            )
            actions[action_id] = action
            payload["actions"] = actions
            _write_payload(repo, payload)

        commit = _introduce_active(action, doc, owner_root=owner_root)
        active_path = owner_root / str(action["intended_active_path"])
        blob = _digest(active_path.read_bytes())
        if blob != action["intended_document_digest"]:
            raise FeatureRepairError(
                "committed repair document does not match prepared digest"
            )
        attempts = list(action.get("attempts") or [])
        if attempts:
            attempts[-1] = {
                **attempts[-1],
                "outcome": "succeeded",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        action.update(
            phase="parent_enabled",
            introduction_commit=commit,
            introduction_blob=blob,
            source_head_after_introduction=head_sha(owner_root),
            target_head_after_introduction=head_sha(
                resolve_mutation_owner(str(action["epic_id"]), trunk=repo)
            ),
            introduced_at=datetime.now(timezone.utc).isoformat(),
            next_action="resume_original_task_delivery"
            if task_id
            else "mint_reserved_task",
            blocker=None,
            attempts=attempts,
        )
        actions[action_id] = action
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _result(action, replayed=existing is not None)


def _current_feature(feature_id: str, root: Path):
    board = merged_board(root)
    meta = board.by_id.get(feature_id)
    if meta is None or meta.tier != "feature":
        raise FeatureRepairError(f"unknown feature {feature_id}")
    owner_root = resolve_mutation_owner(feature_id, trunk=root)
    try:
        doc = parse_doc(
            next(
                path
                for path in (owner_root / "docs/features").glob("*/*.md")
                if path.stem == feature_id or path.stem.startswith(feature_id + "_")
            )
        )
    except (StopIteration, OSError):
        raise FeatureRepairError(
            "exact feature mutation owner is unavailable"
        ) from None
    return doc, owner_root


def _prepare_action(
    feature_id: str,
    request_id: str,
    *,
    action_id: str,
    generation: int,
    task_id: str | None,
    approval_reference: str | None,
    scope_reference: str | None,
    claim_owner: str | None,
    root: Path,
) -> dict[str, Any]:
    doc, owner_root = _current_feature(feature_id, root)
    _admission_gates(doc, task_id=task_id, root=root)
    prior_path = doc.meta.path.resolve().relative_to(owner_root.resolve()).as_posix()
    prior_digest = _digest(doc.meta.path.read_bytes())
    active_rel = f"docs/features/2_active/{doc.meta.path.name}"
    marker = f"{_MARKER_PREFIX} action_id={action_id} generation={generation} -->"
    if marker not in doc.body:
        doc.body = doc.body.rstrip() + "\n\n" + marker + "\n"
    doc.meta.status = "active"
    doc.meta.updated = date.today()
    doc.meta.path = owner_root / active_rel
    intended = render_doc(doc)
    epic_id = str(doc.meta.parent)
    target_root = resolve_mutation_owner(epic_id, trunk=root)
    owner_fingerprint = _digest(
        "\0".join(
            (
                str(root.resolve()),
                str(owner_root.resolve()),
                feature_id,
                epic_id,
                prior_path,
            )
        )
    )
    gate_fingerprint = _digest(
        "\0".join(
            (
                feature_id,
                epic_id,
                request_id,
                task_id or "",
                doc.meta.approved_at.isoformat() if doc.meta.approved_at else "",
                approval_reference or "",
                scope_reference or "",
                prior_digest,
            )
        )
    )
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "kind": "feature_repair",
        "action_id": action_id,
        "request_id": request_id,
        "feature_id": feature_id,
        "task_id": task_id,
        "epic_id": epic_id,
        "generation": generation,
        "gate_fingerprint": gate_fingerprint,
        "owner_fingerprint": owner_fingerprint,
        "claim_owner": claim_owner,
        "approval_reference": approval_reference,
        "approved_at": doc.meta.approved_at.isoformat()
        if doc.meta.approved_at
        else None,
        "scope_reference": scope_reference,
        "prior_document_path": prior_path,
        "prior_document_digest": prior_digest,
        "intended_active_path": active_rel,
        "intended_document_digest": _digest(intended),
        "source_ref": integration_branch("feature", feature_id),
        "target_ref": integration_branch("epic", epic_id),
        "source_head": head_sha(owner_root),
        "target_head": head_sha(target_root),
        "phase": "prepared",
        "blocker": None,
        "next_action": "record_feature_repair_authority",
        "attempts": [{"attempt": 1, "admitted_at": now, "outcome": None}],
        "created_at": now,
        "updated_at": now,
    }


def _prepare_open_review_action(
    feature_id: str,
    request_id: str,
    *,
    action_id: str,
    generation: int,
    request: Mapping[str, Any],
    claim_owner: str | None,
    root: Path,
) -> dict[str, Any]:
    """Snapshot request and intended introduction before any queue authority."""

    doc, owner_root = _current_feature(feature_id, root)
    prior_path = doc.meta.path.resolve().relative_to(owner_root.resolve()).as_posix()
    prior_digest = _digest(doc.meta.path.read_bytes())
    active_rel = f"docs/features/2_active/{doc.meta.path.name}"
    marker = f"{_MARKER_PREFIX} action_id={action_id} generation={generation} -->"
    if marker not in doc.body:
        doc.body = doc.body.rstrip() + "\n\n" + marker + "\n"
    doc.meta.status = "active"
    doc.meta.updated = date.today()
    doc.meta.path = owner_root / active_rel
    intended = render_doc(doc)
    epic_id = str(doc.meta.parent or "")
    owner_fingerprint = _digest(
        "\0".join(
            (str(root.resolve()), str(owner_root.resolve()), feature_id, epic_id, prior_path)
        )
    )
    now = datetime.now(timezone.utc).isoformat()
    request_copy = _copy(request)
    return {
        "schema_version": 2,
        "kind": "feature_repair",
        "repair_route": "open_review",
        "action_id": action_id,
        "request_id": request_id,
        "request_digest": _request_digest(request_copy),
        "reason": request_copy["reason"],
        "request_evidence": request_copy["evidence"],
        "request_authority": request_copy["authority"],
        "feature_id": feature_id,
        "accountable_feature_id": feature_id,
        "task_id": None,
        "epic_id": epic_id,
        "generation": generation,
        "review_generation": request_copy["observed_review_generation"],
        "review_url": request_copy["review_url"],
        "review_forge": request_copy["review_forge"],
        "source_ref": request_copy["source_ref"],
        "target_ref": request_copy["target_ref"],
        "source_head": request_copy["observed_source_head"],
        "target_head": request_copy["observed_target_head"],
        "owner_fingerprint": owner_fingerprint,
        "claim_owner": claim_owner,
        "claim_id": request_copy.get("claim_id"),
        "incident_budget_id": request_copy.get("incident_budget_id"),
        "approval_reference": request_copy["approval_reference"],
        "approved_at": doc.meta.approved_at.isoformat() if doc.meta.approved_at else None,
        "scope_reference": request_copy["scope_reference"],
        "prior_document_path": prior_path,
        "prior_document_digest": prior_digest,
        "intended_active_path": active_rel,
        "intended_document_digest": _digest(intended),
        "phase": "prepared",
        "blocker": None,
        "next_action": "record_feature_repair_authority",
        "attempts": [{"attempt": 1, "admitted_at": now, "outcome": None}],
        "created_at": now,
        "updated_at": now,
    }


def _review_request_comment_id(action: Mapping[str, Any]) -> str | None:
    """Return the one comment durably identified as this review fix request."""

    request_id = action.get("request_id")
    scope_reference = action.get("scope_reference")
    evidence = action.get("request_evidence")
    if (
        not isinstance(request_id, str)
        or not request_id.startswith("review-fix:")
        or not isinstance(scope_reference, str)
        or not scope_reference.startswith("review-comment:")
        or not isinstance(evidence, Mapping)
    ):
        return None
    request_comment_id = request_id.removeprefix("review-fix:")
    scope_comment_id = scope_reference.removeprefix("review-comment:")
    evidence_comment_id = evidence.get("comment_id")
    if (
        request_comment_id
        and request_comment_id == scope_comment_id == evidence_comment_id
    ):
        return request_comment_id
    return None


def _open_review_admission_gates(
    action: Mapping[str, Any], doc, *, owner_root: Path, root: Path
) -> None:
    from cascade.review import review_record_for_feature

    if doc.meta.status not in {"completed", "active"}:
        raise _FeatureRepairRefusal(
            "feature_not_repairable", "restore_open_feature_lifecycle", terminal=True
        )
    board = merged_board(root)
    parent = board.by_id.get(doc.meta.parent) if doc.meta.parent else None
    if parent is None or parent.tier != "epic" or parent.status != "active":
        raise _FeatureRepairRefusal("parent_not_active", "activate_accountable_epic")
    authority = action.get("request_authority")
    if not isinstance(authority, Mapping):
        raise _FeatureRepairRefusal(
            "request_authority_missing", "authenticate_repair_request", terminal=True
        )
    if authority.get("kind") == "parent" and authority.get("id") != doc.meta.parent:
        raise _FeatureRepairRefusal(
            "parent_authority_changed", "request_from_current_parent", terminal=True
        )
    if authority.get("kind") not in {"parent", "authenticated_human"}:
        raise _FeatureRepairRefusal(
            "request_authority_invalid", "authenticate_repair_request", terminal=True
        )

    record = review_record_for_feature(doc.meta.id, root=root)
    if record is None:
        raise _FeatureRepairRefusal("review_evidence_missing", "restore_review_registry")
    if record.get("closed") or record.get("forge_acceptance") or record.get(
        "stacked_acceptance"
    ):
        raise _FeatureRepairRefusal(
            "review_is_not_open", "use_accepted_review_followup", terminal=True
        )
    forge_state = str(record.get("state") or record.get("forge_state") or "open").lower()
    if forge_state not in {"open", "awaiting_review", ""}:
        raise _FeatureRepairRefusal(
            "review_is_not_open", "refresh_or_reopen_original_review"
        )
    expected = {
        "review_url": record.get("url") or record.get("review_url"),
        "review_forge": record.get("forge"),
        "source_ref": record.get("source_branch"),
        "target_ref": record.get("target_branch"),
        "source_head": record.get("source_head"),
        "target_head": record.get("target_head"),
        "review_generation": int(record.get("current_generation") or 0),
    }
    if any(action.get(key) != value for key, value in expected.items()):
        raise _FeatureRepairRefusal(
            "stale_review_evidence", "refresh_review_observation"
        )
    if action.get("source_ref") != integration_branch("feature", doc.meta.id) or action.get(
        "target_ref"
    ) != integration_branch("epic", str(doc.meta.parent)):
        raise _FeatureRepairRefusal(
            "review_route_changed", "restore_original_review_route", terminal=True
        )

    for dep in doc.meta.depends_on:
        candidate = board.by_id.get(dep)
        if candidate is None or candidate.status != "completed":
            raise _FeatureRepairRefusal(
                "feature_dependency_incomplete", f"complete_dependency:{dep}"
            )
    gate = blocking_threads_for(doc.meta.id, root=root, board=board)
    request_comment_id = _review_request_comment_id(action)
    unexpected = [
        thread for thread in gate.threads if thread.id != request_comment_id
    ]
    if unexpected:
        raise _FeatureRepairRefusal(
            "governing_comments_changed", "resolve_or_refresh_governing_comments"
        )

    if action.get("phase") in {"prepared", "authority_recorded", "waiting"}:
        if head_sha(owner_root) != action.get("source_head"):
            raise _FeatureRepairRefusal(
                "stale_source_head", "refresh_review_observation"
            )
        target_root = resolve_mutation_owner(str(doc.meta.parent), trunk=root)
        if head_sha(target_root) != action.get("target_head"):
            raise _FeatureRepairRefusal(
                "stale_target_head", "refresh_review_observation"
            )

    budget_id = action.get("incident_budget_id")
    if budget_id is not None:
        budgets = _read_payload(root).get("incident_budgets")
        budget = budgets.get(budget_id) if isinstance(budgets, Mapping) else None
        if not isinstance(budget, Mapping):
            raise _FeatureRepairRefusal(
                "incident_budget_missing", "restore_original_incident_budget"
            )
        if budget.get("status") != "active":
            raise _FeatureRepairRefusal(
                "incident_budget_unavailable", "reconcile_original_incident_budget"
            )
        live_claim = budget.get("live_claim")
        if isinstance(live_claim, Mapping) and live_claim.get("claim_id") != action.get(
            "claim_id"
        ):
            raise _FeatureRepairRefusal(
                "incident_claim_changed", "join_current_incident_claim"
            )


def _admission_gates(doc, *, task_id: str | None, root: Path) -> None:
    if doc.meta.status not in {"completed", "active"}:
        raise FeatureRepairError(
            "feature repair requires an active or completed Feature"
        )
    if not doc.meta.parent:
        raise FeatureRepairError("feature repair parent is unknown")
    board = merged_board(root)
    parent = board.by_id.get(doc.meta.parent)
    if parent is None or parent.tier != "epic" or parent.status != "active":
        raise FeatureRepairError(
            "feature repair requires an eligible active Epic target"
        )
    if doc.meta.approved_at is None:
        raise FeatureRepairError("feature repair approval is missing")
    if blocked := refusal_if_blocked(doc.meta.id, root=root, board=board):
        raise FeatureRepairError(blocked)
    try:
        owner_root = git_root_for_path(doc.meta.path)
    except GitError as exc:
        raise FeatureRepairError("feature repair checkout is unavailable") from exc
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=owner_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise FeatureRepairError("feature repair checkout is dirty or unreadable")
    for dep in doc.meta.depends_on:
        candidate = board.by_id.get(dep)
        if candidate is None or candidate.status != "completed":
            raise FeatureRepairError(f"feature dependency {dep} is not completed")
    if task_id is not None:
        task = board.by_id.get(task_id)
        if task is None or task.tier != "task" or task.parent != doc.meta.id:
            raise FeatureRepairError("repair Task is not an existing direct child")
        if execution_lease_is_live(task_id, root=root):
            raise FeatureRepairError("live execution owns the repair Task")


def _recheck_action(
    action: Mapping[str, Any], doc, *, owner_root: Path, task_id: str | None, root: Path
) -> None:
    if (
        action.get("feature_id") != doc.meta.id
        or action.get("epic_id") != doc.meta.parent
    ):
        raise FeatureRepairError("feature repair ownership changed")
    if doc.meta.approved_at is None or doc.meta.approved_at.isoformat() != action.get(
        "approved_at"
    ):
        if action.get("repair_route") == "open_review":
            raise _FeatureRepairRefusal(
                "feature_approval_changed", "restore_or_refresh_feature_approval"
            )
        raise FeatureRepairError("feature repair approval changed")
    target_root = resolve_mutation_owner(str(doc.meta.parent), trunk=root)
    expected_target = (
        action.get("target_head_after_introduction")
        if action.get("phase") not in {"prepared", "authority_recorded"}
        else action.get("target_head")
    )
    if head_sha(target_root) != expected_target:
        if action.get("repair_route") == "open_review":
            raise _FeatureRepairRefusal(
                "stale_target_head", "refresh_review_observation"
            )
        raise FeatureRepairError("feature repair target head changed")
    expected_owner = _digest(
        "\0".join(
            (
                str(root.resolve()),
                str(owner_root.resolve()),
                doc.meta.id,
                str(doc.meta.parent),
                str(action["prior_document_path"]),
            )
        )
    )
    if expected_owner != action.get("owner_fingerprint"):
        raise FeatureRepairError("feature repair mutation owner changed")
    if action.get("repair_route") == "open_review":
        _open_review_admission_gates(
            action, doc, owner_root=owner_root, root=root
        )
    else:
        _admission_gates(doc, task_id=task_id or action.get("task_id"), root=root)
    current_rel = doc.meta.path.resolve().relative_to(owner_root.resolve()).as_posix()
    current_digest = _digest(doc.meta.path.read_bytes())
    allowed = {
        (action.get("prior_document_path"), action.get("prior_document_digest")),
        (action.get("intended_active_path"), action.get("intended_document_digest")),
    }
    if (current_rel, current_digest) not in allowed:
        raise FeatureRepairError("feature repair document changed after admission")


def _introduce_active(
    action: Mapping[str, Any], doc, *, owner_root: Path
) -> str | None:
    active_path = owner_root / str(action["intended_active_path"])
    if (
        active_path.exists()
        and _digest(active_path.read_bytes()) == action["intended_document_digest"]
    ):
        rel = active_path.relative_to(owner_root)
        return last_commit_touching(owner_root, rel)
    marker = f"{_MARKER_PREFIX} action_id={action['action_id']} generation={action['generation']} -->"
    if marker not in doc.body:
        doc.body = doc.body.rstrip() + "\n\n" + marker + "\n"
    previous = doc.meta.path
    doc.meta.status = "active"
    doc.meta.updated = date.today()
    doc.meta.path = active_path
    commit = save_doc(doc, previous_path=previous, root=owner_root)
    if commit is not None:
        blob = read_blob(owner_root, commit, str(action["intended_active_path"]))
        if _digest(blob) != action["intended_document_digest"]:
            raise FeatureRepairError(
                "introduction commit contains the wrong Feature blob"
            )
    return commit


def repair_event_authorizes(meta, event: Event, *, root: Path) -> bool:
    """Return true only for the exact fenced active introduction."""

    if (
        event.type != "FeatureRepairAuthorized"
        or event.payload.get("feature_id") != meta.id
    ):
        return False
    action_id = event.payload.get("action_id")
    generation = event.payload.get("generation")
    if not isinstance(action_id, str) or not isinstance(generation, int):
        return False
    try:
        with task_lifecycle_read_lock(root=root):
            action = _actions(_read_payload(root)).get(action_id)
    except ActionRecoveryUnavailable:
        return False
    if (
        action is None
        or action.get("kind") != "feature_repair"
        or action.get("phase") not in _ACTIVE_PHASES
    ):
        return False
    bindings = {
        "feature_id": meta.id,
        "generation": generation,
        "authority_event_id": event.payload.get("event_id"),
        "owner_fingerprint": event.payload.get("owner_fingerprint"),
        "source_ref": event.payload.get("source_ref"),
        "target_ref": event.payload.get("target_ref"),
        "source_head": event.payload.get("source_head"),
        "target_head": event.payload.get("target_head"),
        "request_digest": event.payload.get("request_digest"),
        "review_url": event.payload.get("review_url"),
        "review_generation": event.payload.get("review_generation"),
        "claim_id": event.payload.get("claim_id"),
        "incident_budget_id": event.payload.get("incident_budget_id"),
        "intended_active_path": event.payload.get("intended_active_path"),
        "intended_document_digest": event.payload.get("document_digest"),
    }
    if any(action.get(key) != value for key, value in bindings.items()):
        return False
    try:
        owner_root = git_root_for_path(meta.path)
        rel = meta.path.resolve().relative_to(owner_root.resolve()).as_posix()
        if rel != action["intended_active_path"]:
            return False
        commit = action.get("introduction_commit")
        if commit:
            from cascade.workspace.trunk import _is_ancestor

            current_head = head_sha(owner_root)
            if current_head is None or not _is_ancestor(
                owner_root, commit, current_head
            ):
                return False
            if _digest(read_blob(owner_root, commit, rel)) != action.get(
                "introduction_blob"
            ):
                return False
            # Later Feature-team edits are legitimate descendants of the
            # introduction.  They retain the immutable marker; authority is
            # proven by the recorded introduction blob, not by requiring the
            # active document to remain forever byte-identical.
            marker = (
                f"{_MARKER_PREFIX} action_id={action_id} generation={generation} -->"
            )
            if marker not in meta.path.read_text(encoding="utf-8"):
                return False
        elif _digest(meta.path.read_bytes()) != action["intended_document_digest"]:
            # Move/checkpoint gap: only the prepared exact bytes are accepted.
            return False
    except (GitError, OSError, KeyError, ValueError):
        return False
    return True


register_feature_tool("feature_repair", feature_repair)
