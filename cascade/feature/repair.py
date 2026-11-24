"""Generation-bound admission of late work to an existing Feature.

The repair receipt is deliberately stored in the existing action ledger.  A
queue event by itself is not authority: the watchdog joins it to this receipt
and to the exact active document bytes before allowing the introduction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from cascade.board.errors import GitError
from cascade.board.gitutil import head_sha, last_commit_touching, read_blob
from cascade.board.parse import parse_doc, render_doc
from cascade.board.store import save_doc
from cascade.comments.gate import refusal_if_blocked
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
from cascade.watchdog.events import append_event
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


class FeatureRepairError(ValueError):
    """The exact Feature repair cannot be admitted or resumed."""


def _digest(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _stable_action_id(feature_id: str, request_id: str) -> str:
    value = _digest(f"feature_repair\0{feature_id}\0{request_id}")[:24]
    return f"feature_repair:{feature_id}:{value}"


def _copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value)))


def _result(action: Mapping[str, Any], *, replayed: bool = False) -> dict[str, Any]:
    return {
        "ok": not str(action.get("phase", "")).startswith(("blocked", "superseded")),
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
) -> dict[str, Any]:
    """Inspect, admit, or resume an exact generation-bound Feature repair.

    ``request_id`` is the queued Task delivery action (or reserved mint request)
    identity.  It, rather than a caller-selected role, supplies replay identity.
    """

    if operation == "inspect":
        return inspect_feature_repair(feature_id, request_id, root=root)
    if operation not in {"admit", "resume"}:
        raise FeatureRepairError(f"unknown feature repair operation: {operation}")
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
) -> dict[str, Any]:
    if not feature_id.startswith("feat_") or not request_id.strip():
        raise FeatureRepairError(
            "feature_id and request_id must be stable nonempty identities"
        )
    action_id = _stable_action_id(feature_id, request_id)
    repo = lifecycle_root(root)
    with task_lifecycle_lock(root=repo):
        payload = _read_payload(repo)
        actions = _actions(payload)
        existing = actions.get(action_id)
        if existing is not None:
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
            action = _prepare_action(
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
            actions[action_id] = action
            payload["version"] = max(int(payload.get("version") or 1), 3)
            payload["actions"] = actions
            _write_payload(repo, payload)

        if existing is not None and action.get("phase") in {
            "prepared",
            "authority_recorded",
        }:
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
        _recheck_action(action, doc, owner_root=owner_root, task_id=task_id, root=repo)
        if action.get("phase") not in {"prepared", "authority_recorded"}:
            return _result(action, replayed=True)
        event_id = str(
            action.get("authority_event_id") or f"{action_id}:g{action['generation']}"
        )
        if action.get("phase") == "prepared":
            append_event(
                feature_id,
                Event(
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
                        "intended_active_path": action["intended_active_path"],
                        "document_digest": action["intended_document_digest"],
                    },
                    dest=feature_id,
                ),
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
        raise FeatureRepairError("feature repair approval changed")
    target_root = resolve_mutation_owner(str(doc.meta.parent), trunk=root)
    expected_target = (
        action.get("target_head_after_introduction")
        if action.get("phase") not in {"prepared", "authority_recorded"}
        else action.get("target_head")
    )
    if head_sha(target_root) != expected_target:
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
