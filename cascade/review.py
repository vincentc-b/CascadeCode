"""Feature draft-MR lifecycle and review-comment delivery."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import urlsplit

from cascade.board.errors import BoardError, GitError, NotFound
from cascade.board.gitutil import head_sha
from cascade.board.store import (
    list_board,
    move_doc,
    read_doc,
    read_doc_in_worktree,
    save_doc,
)
from cascade.board.types import BoardIndex, WorkMeta
from cascade.tracking import (
    MergeRequest,
    ReviewNotFound,
    create_merge_request,
    detect_forge,
    find_merge_request,
    fast_forward_branch,
    forge_ready,
    merge_request_snapshot,
    push_branch,
    reply_to_merge_request,
)
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    is_trunk_pointer,
    load_registry,
    locate_trunk,
    merged_board,
)

_LOG = logging.getLogger(__name__)

_REVIEW_EVIDENCE_MAX_BYTES = 32 * 1024
_REVIEW_EVIDENCE_MAX_IDENTITY_BYTES = 256
_REVIEW_EVIDENCE_MAX_INTEGER_DIGITS = 64
_REVIEW_EVIDENCE_MAX_CHECK_ROWS = 20
_REVIEW_EVIDENCE_UNAVAILABLE = "review_evidence_out_of_bounds"


@dataclass(frozen=True)
class OpenReviewContext:
    feature_id: str
    epic_id: str | None
    feature_title: str | None
    epic_title: str | None


@dataclass(frozen=True)
class OpenReview:
    """Read-model row for one open entry in the durable review registry."""

    id: str
    url: str
    state: str
    context: OpenReviewContext
    details: dict[str, object]


EpicCloseStage = Literal["implementation_review_pending", "completed", "blocked"]
ForgeReviewState = Literal["open", "merged", "closed", "unknown"]


@dataclass(frozen=True)
class EpicCloseBlocker:
    """Operator-actionable reason an epic close cannot currently advance."""

    code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not self.code.strip() or any(char.isspace() for char in self.code):
            raise ValueError(
                "epic close blocker code must be non-blank and contain no whitespace"
            )
        if not self.message.strip() or "\n" in self.message or "\r" in self.message:
            raise ValueError(
                "epic close blocker message must be a non-blank single line"
            )
        if not isinstance(self.retryable, bool):
            raise ValueError("epic close blocker retryable must be boolean")


@dataclass(frozen=True)
class EpicReviewSnapshot:
    """Durable state for the one implementation review that closes an epic."""

    stage: EpicCloseStage
    review_url: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    forge_state: ForgeReviewState = "unknown"
    blocker: EpicCloseBlocker | None = None

    def __post_init__(self) -> None:
        if self.stage not in {"implementation_review_pending", "completed", "blocked"}:
            raise ValueError(f"invalid epic close stage: {self.stage!r}")
        if self.forge_state not in {"open", "merged", "closed", "unknown"}:
            raise ValueError(f"invalid forge review state: {self.forge_state!r}")
        if self.review_url is not None:
            validate_review_url(self.review_url)
        for label, branch in (
            ("source", self.source_branch),
            ("target", self.target_branch),
        ):
            if branch is not None and (
                not branch.strip() or "\n" in branch or "\r" in branch
            ):
                raise ValueError(f"{label} branch must be a non-blank single line")
        if self.stage == "implementation_review_pending":
            if not self.review_url or not self.source_branch or not self.target_branch:
                raise ValueError(
                    "pending epic review requires URL, source branch, and target branch"
                )
            if self.blocker is not None:
                raise ValueError("pending epic review cannot also have a blocker")
        if self.stage == "blocked" and self.blocker is None:
            raise ValueError("blocked epic close requires actionable blocker details")
        if self.stage != "blocked" and self.blocker is not None:
            raise ValueError("epic close blocker is only valid for the blocked stage")


def validate_review_url(url: str) -> None:
    """Reject non-web, relative, or credential-bearing review links."""

    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "review URL must be an absolute HTTP(S) URL without credentials"
        )


def epic_review_snapshot(epic_id: str, *, root: Path) -> EpicReviewSnapshot | None:
    """Load an epic snapshot, accepting records written before typed fields existed."""

    record = _load(locate_trunk(root)).get(epic_id)
    if not isinstance(record, dict):
        return None
    kind = record.get("kind")
    if kind not in (None, "epic_close"):
        return None
    # Legacy epic records contained only MergeRequest fields. Infer the new
    # fields rather than making a rolling upgrade destructive.
    stage = str(record.get("stage") or "implementation_review_pending")
    forge_state = str(
        record.get("forge_state") or ("merged" if record.get("closed") else "open")
    )
    blocker_raw = record.get("blocker")
    blocker = None
    if isinstance(blocker_raw, dict):
        blocker = EpicCloseBlocker(
            code=str(blocker_raw.get("code") or ""),
            message=str(blocker_raw.get("message") or ""),
            retryable=blocker_raw.get("retryable"),  # type: ignore[arg-type]
        )
    return EpicReviewSnapshot(
        stage=stage,  # type: ignore[arg-type]
        review_url=str(record.get("review_url") or record.get("url") or "") or None,
        source_branch=str(record.get("source_branch") or "") or None,
        target_branch=str(record.get("target_branch") or "") or None,
        forge_state=forge_state,  # type: ignore[arg-type]
        blocker=blocker,
    )


def epic_close_document_staged(meta: WorkMeta, *, root: Path) -> bool:
    """True when a completed epic document still belongs to its review worktree."""

    if (
        meta.tier != "epic"
        or meta.status != "completed"
        or meta.path.parent.name != "3_completed"
    ):
        return False
    entry = get_integration_worktree(locate_trunk(root), "epic", meta.id)
    return entry is not None and meta.path.resolve().is_relative_to(
        entry.path.resolve()
    )


def epic_close_documents_staged(
    metas: list[WorkMeta], *, root: Path
) -> dict[str, bool]:
    """Project completed epic staging from one request-local registry snapshot."""

    candidates = [
        meta
        for meta in metas
        if meta.tier == "epic"
        and meta.status == "completed"
        and meta.path.parent.name == "3_completed"
    ]
    if not candidates:
        return {}
    entries = {}
    for entry in load_registry(locate_trunk(root)):
        if entry.kind == "epic":
            # Match get_integration_worktree's first-record semantics.
            entries.setdefault(entry.work_id, entry)
    return {
        meta.id: (entry := entries.get(meta.id)) is not None
        and meta.path.resolve().is_relative_to(entry.path.resolve())
        for meta in candidates
    }


def persist_epic_review_snapshot(
    epic_id: str, snapshot: EpicReviewSnapshot, *, root: Path
) -> None:
    """Atomically persist the validated epic close snapshot in the review registry."""

    blocker = snapshot.blocker
    record: dict[str, object] = {
        "kind": "epic_close",
        "stage": snapshot.stage,
        "review_url": snapshot.review_url,
        # Keep ``url`` for existing registry consumers and rolling upgrades.
        "url": snapshot.review_url,
        "source_branch": snapshot.source_branch,
        "target_branch": snapshot.target_branch,
        "forge_state": snapshot.forge_state,
        "closed": snapshot.stage == "completed",
        # Explicitly clear a prior lookup blocker when a later refresh works.
        "blocker": None,
    }
    if blocker is not None:
        record["blocker"] = {
            "code": blocker.code,
            "message": blocker.message,
            "retryable": blocker.retryable,
        }
    _update_record(locate_trunk(root), epic_id, record, create=True)


def refresh_epic_review_snapshot(
    epic_id: str, *, root: Path
) -> EpicReviewSnapshot | None:
    """Refresh a durable epic review from the forge without creating a review.

    The persisted URL is the review identity.  Lookup failures deliberately
    retain that identity and branch context so a later retry cannot fall back
    to publication and accidentally create a replacement review.
    """

    trunk = locate_trunk(root)
    current = epic_review_snapshot(epic_id, root=trunk)
    if current is None:
        return None
    if current.review_url is None:
        return _persist_epic_review_blocker(
            epic_id,
            current,
            root=trunk,
            code="review_identity_missing",
            message="Restore the stored review URL before retrying epic close.",
            retryable=False,
        )
    forge = detect_forge(trunk)
    if forge is None:
        return _persist_epic_review_blocker(
            epic_id,
            current,
            root=trunk,
            code="review_lookup_failed",
            message="Retry after configuring a supported forge remote.",
            retryable=True,
        )
    review = MergeRequest(
        url=current.review_url,
        number=None,
        forge=forge,
        source_branch=current.source_branch or "",
        target_branch=current.target_branch or "",
        draft=False,
    )
    try:
        live = merge_request_snapshot(trunk, review)
    except (NotFound, ReviewNotFound):
        return _persist_epic_review_blocker(
            epic_id,
            current,
            root=trunk,
            code="review_missing",
            message="Restore access to the existing forge review or verify that it still exists.",
            retryable=False,
        )
    except (GitError, OSError, ValueError):
        return _persist_epic_review_blocker(
            epic_id,
            current,
            root=trunk,
            code="review_lookup_failed",
            message="Retry after restoring forge connectivity and credentials.",
            retryable=True,
        )

    raw_state = str(live.get("state") or "").lower()
    forge_state: ForgeReviewState = (
        raw_state if raw_state in {"open", "merged", "closed"} else "unknown"
    )  # type: ignore[assignment]
    if forge_state == "open":
        refreshed = EpicReviewSnapshot(
            stage="implementation_review_pending",
            review_url=current.review_url,
            source_branch=current.source_branch,
            target_branch=current.target_branch,
            forge_state=forge_state,
        )
    elif forge_state == "merged":
        # The forge merge is necessary but not sufficient for terminal epic
        # completion; close reconciliation still verifies the landed document.
        refreshed = EpicReviewSnapshot(
            stage="implementation_review_pending",
            review_url=current.review_url,
            source_branch=current.source_branch,
            target_branch=current.target_branch,
            forge_state=forge_state,
        )
    else:
        code = "review_closed" if forge_state == "closed" else "review_state_unknown"
        message = (
            "Reopen the existing forge review before retrying epic close."
            if forge_state == "closed"
            else "Retry after the forge reports a recognized review state."
        )
        refreshed = EpicReviewSnapshot(
            stage="blocked",
            review_url=current.review_url,
            source_branch=current.source_branch,
            target_branch=current.target_branch,
            forge_state=forge_state,
            blocker=EpicCloseBlocker(
                code=code,
                message=message,
                retryable=forge_state == "unknown",
            ),
        )
    persist_epic_review_snapshot(epic_id, refreshed, root=trunk)
    return refreshed


def _persist_epic_review_blocker(
    epic_id: str,
    current: EpicReviewSnapshot,
    *,
    root: Path,
    code: str,
    message: str,
    retryable: bool,
) -> EpicReviewSnapshot:
    blocked = EpicReviewSnapshot(
        stage="blocked",
        review_url=current.review_url,
        source_branch=current.source_branch,
        target_branch=current.target_branch,
        forge_state="unknown",
        blocker=EpicCloseBlocker(code=code, message=message, retryable=retryable),
    )
    persist_epic_review_snapshot(epic_id, blocked, root=root)
    return blocked


def list_open_reviews(*, root: Path, limit: int | None = None) -> list[OpenReview]:
    """Return open registry rows without mutating durable review state."""

    if limit is not None and limit < 0:
        raise ValueError("open review limit cannot be negative")

    trunk = locate_trunk(root)
    state = _load(trunk)
    from cascade.workspace.integration_worktree import merged_board_readonly

    board = merged_board_readonly(trunk)
    open_ids = [
        feature_id
        for feature_id in sorted(state)
        if isinstance(state[feature_id], dict)
        and not state[feature_id].get("closed")
        and state[feature_id].get("kind") != "epic_close"
        and _stacked_acceptance(state[feature_id]) is None
        and _forge_acceptance(state[feature_id]) is None
        and str(state[feature_id].get("url") or "").strip()
    ]
    if limit is not None:
        open_ids = open_ids[:limit]
    projections = feature_review_views(open_ids, root=trunk, board_snapshot=board)
    rows: list[OpenReview] = []
    for feature_id in open_ids:
        record = state[feature_id]
        url = str(record.get("url") or "").strip()
        epic_id = _review_target_epic(record)
        feature_meta = board.by_id.get(feature_id)
        epic_meta = board.by_id.get(epic_id) if epic_id else None
        projection = projections.get(feature_id) or {}
        rows.append(
            OpenReview(
                id=feature_id,
                url=url,
                state=str(projection.get("state") or "awaiting_review"),
                context=OpenReviewContext(
                    feature_id=feature_id,
                    epic_id=epic_id,
                    feature_title=feature_meta.title if feature_meta else None,
                    epic_title=epic_meta.title if epic_meta else None,
                ),
                details=projection,
            )
        )
    return rows


def _state_path(root: Path) -> Path:
    return Path(root) / ".cascade" / "reviews.json"


def review_record_for_feature(
    feature_id: str, *, root: Path
) -> dict[str, object] | None:
    trunk = locate_trunk(root)
    record = _load(trunk).get(feature_id)
    return dict(record) if isinstance(record, dict) else None


def _review_evidence_name(value: object) -> str:
    """Return one exact check identity or refuse the complete observation."""

    if not isinstance(value, str):
        raise ValueError("check name must be a string")
    if len(value.encode("utf-8")) > _REVIEW_EVIDENCE_MAX_IDENTITY_BYTES:
        raise ValueError("check name exceeds the UTF-8 byte limit")
    return value


def _review_evidence_generation(value: object) -> str | int | None:
    """Keep an authoritative generation losslessly within its scalar bound."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("check generation must be a string or integer")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _REVIEW_EVIDENCE_MAX_IDENTITY_BYTES:
            raise ValueError("string check generation exceeds the UTF-8 byte limit")
        return value
    if len(str(abs(value))) > _REVIEW_EVIDENCE_MAX_INTEGER_DIGITS:
        raise ValueError("integer check generation exceeds the decimal-digit limit")
    return value


def _review_evidence_unavailable_marker(observed_at: str) -> dict[str, object]:
    return {
        "review_health": {
            "state": "unavailable",
            "reason": _REVIEW_EVIDENCE_UNAVAILABLE,
            "checks": [],
            "checks_omitted": 0,
        },
        "required_check_policy": {
            "available": False,
            "error": _REVIEW_EVIDENCE_UNAVAILABLE,
            "source_head": None,
            "target_head": None,
            "required": [],
            "required_omitted": 0,
        },
        "required_check_results": {
            "available": False,
            "error": _REVIEW_EVIDENCE_UNAVAILABLE,
            "source_head": None,
            "generation": None,
            "statuses": {},
            "checks": {},
            "checks_omitted": 0,
        },
        "review_feedback": {
            "available": False,
            "error": _REVIEW_EVIDENCE_UNAVAILABLE,
            "approval_state": None,
            "actionable": False,
            "actionable_count": 0,
        },
        "review_observed_at": observed_at,
    }


def _review_evidence_payload_within_bound(value: object) -> bool:
    """Return whether one legacy/fallback evidence payload is safely normalizable."""

    try:
        serialized = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return False
    return len(serialized) <= _REVIEW_EVIDENCE_MAX_BYTES


def record_feature_review_evidence(
    feature_id: str, snapshot: Mapping[str, object], *, root: Path
) -> bool:
    """Persist a bounded normalized forge observation in the review registry.

    Forge access belongs to the review-health worker.  Read APIs consume this
    current observation later and therefore never need transport authority.
    """

    def text(value: object, limit: int = 160) -> str | None:
        if not isinstance(value, str):
            return None
        value = " ".join(value.split())
        return value[:limit] if value else None

    observed_at = datetime.now(timezone.utc).isoformat()
    trunk = locate_trunk(root)
    try:
        health_raw = snapshot.get("review_health")
        health_raw = health_raw if isinstance(health_raw, Mapping) else {}
        health_checks_raw = health_raw.get("checks")
        if health_checks_raw is not None and not isinstance(health_checks_raw, list):
            raise ValueError("health checks must be a list")
        health_names = (
            [_review_evidence_name(name) for name in health_checks_raw]
            if isinstance(health_checks_raw, list)
            else []
        )
        health = {
            "state": text(health_raw.get("state"), 64) or "unknown",
            "reason": text(health_raw.get("reason"), 160),
            "checks": health_names[:_REVIEW_EVIDENCE_MAX_CHECK_ROWS],
            "checks_omitted": max(
                0, len(health_names) - _REVIEW_EVIDENCE_MAX_CHECK_ROWS
            ),
        }

        policy_raw = snapshot.get("required_check_policy")
        policy_raw = policy_raw if isinstance(policy_raw, Mapping) else {}
        required_raw = policy_raw.get("required")
        if required_raw is not None and not isinstance(required_raw, list):
            raise ValueError("required checks must be a list")
        required_names = (
            [_review_evidence_name(name) for name in required_raw]
            if isinstance(required_raw, list)
            else []
        )
        policy = {
            "available": policy_raw.get("available") is True,
            "error": text(policy_raw.get("error")),
            "source_head": text(policy_raw.get("source_head"), 80),
            "target_head": text(policy_raw.get("target_head"), 80),
            "required": required_names[:_REVIEW_EVIDENCE_MAX_CHECK_ROWS],
            "required_omitted": max(
                0, len(required_names) - _REVIEW_EVIDENCE_MAX_CHECK_ROWS
            ),
        }

        results_raw = snapshot.get("required_check_results")
        results_raw = results_raw if isinstance(results_raw, Mapping) else {}
        statuses_raw = results_raw.get("statuses")
        if statuses_raw is not None and not isinstance(statuses_raw, Mapping):
            raise ValueError("check statuses must be a mapping")
        statuses_raw = statuses_raw if isinstance(statuses_raw, Mapping) else {}
        check_results_raw = results_raw.get("checks")
        if check_results_raw is not None and not isinstance(
            check_results_raw, Mapping
        ):
            raise ValueError("check results must be a mapping")
        check_results_raw = (
            check_results_raw if isinstance(check_results_raw, Mapping) else {}
        )
        status_names = [_review_evidence_name(name) for name in statuses_raw]
        check_names = [_review_evidence_name(name) for name in check_results_raw]
        normalized_generations: dict[str, str | int | None] = {}
        for name, raw_check in check_results_raw.items():
            if not isinstance(raw_check, Mapping):
                raise ValueError("check result must be a mapping")
            normalized_generations[name] = _review_evidence_generation(
                raw_check.get("generation")
            )
        all_names = sorted(set(status_names) | set(check_names))
        names = all_names[:_REVIEW_EVIDENCE_MAX_CHECK_ROWS]
        checks: dict[str, object] = {}
        statuses: dict[str, object] = {}
        for name in names:
            check = check_results_raw.get(name)
            check = check if isinstance(check, Mapping) else {}
            status = text(
                statuses_raw.get(name)
                or check.get("status")
                or check.get("conclusion"),
                40,
            )
            statuses[name] = status or "unknown"
            checks[name] = {
                "status": status or "unknown",
                "generation": normalized_generations.get(name),
                "source_head": text(check.get("source_head"), 80),
                "observed_at": text(check.get("observed_at"), 64),
            }
        results = {
            "available": results_raw.get("available") is True,
            "error": text(results_raw.get("error")),
            "source_head": text(results_raw.get("source_head"), 80),
            "generation": _review_evidence_generation(results_raw.get("generation")),
            "statuses": statuses,
            "checks": checks,
            "checks_omitted": max(0, len(all_names) - _REVIEW_EVIDENCE_MAX_CHECK_ROWS),
        }

        feedback_raw = snapshot.get("review_feedback")
        feedback_raw = feedback_raw if isinstance(feedback_raw, Mapping) else {}
        actionable_raw = feedback_raw.get("actionable_feedback")
        feedback = {
            "available": feedback_raw.get("available") is True,
            "error": text(feedback_raw.get("error")),
            "approval_state": text(feedback_raw.get("approval_state"), 40),
            "actionable": feedback_raw.get("actionable") is True,
            "actionable_count": len(actionable_raw[:100])
            if isinstance(actionable_raw, list)
            else 0,
        }
        observation = {
            "review_health": health,
            "required_check_policy": policy,
            "required_check_results": results,
            "review_feedback": feedback,
            "review_observed_at": observed_at,
        }
        serialized = json.dumps(
            observation, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        if len(serialized) > _REVIEW_EVIDENCE_MAX_BYTES:
            raise ValueError("normalized review observation exceeds the byte limit")
    except (TypeError, ValueError, UnicodeError):
        _update_record(
            trunk,
            feature_id,
            _review_evidence_unavailable_marker(observed_at),
        )
        return False
    return _update_record(trunk, feature_id, observation) is not None


def _load(root: Path) -> dict[str, dict[str, object]]:
    path = _state_path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


_GENERATION_CONTAINER_FIELDS = frozenset(
    {"schema_version", "generations", "current_generation"}
)


def _generation_projection(record: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in record.items()
        if key not in _GENERATION_CONTAINER_FIELDS
    }


def _versioned_review_record(
    record: dict[str, object],
    *,
    generation: int,
    action_id: str | None = None,
) -> dict[str, object]:
    """Add immutable-generation storage while retaining compatibility fields."""

    updated = dict(record)
    generations_raw = updated.get("generations")
    generations = dict(generations_raw) if isinstance(generations_raw, dict) else {}
    current_raw = updated.get("current_generation")
    seeded_legacy = False
    if not generations and current_raw is None and record:
        legacy = _generation_projection(record)
        legacy.setdefault("generation", 0)
        legacy.setdefault("action_id", None)
        legacy.setdefault(
            "reconciliation_status",
            "accepted"
            if legacy.get("closed") is True
            and all(
                legacy.get(field)
                for field in (
                    "accepted_merge_sha",
                    "accepted_source_head",
                    "accepted_target_head",
                )
            )
            else "legacy_unverified"
            if legacy.get("closed") is True
            else "pending",
        )
        generations["0"] = legacy
        seeded_legacy = True
    projection = (
        dict(generations["0"])
        if seeded_legacy and generation == 0
        else _generation_projection(record)
    )
    projection["generation"] = generation
    projection["action_id"] = action_id
    projection.setdefault("publication_action_id", action_id)
    projection.setdefault("reconciliation_status", "pending")
    generations[str(generation)] = projection
    updated.update(projection)
    updated["schema_version"] = 2
    updated["generations"] = generations
    updated["current_generation"] = generation
    return updated


def feature_review_generation(
    feature_id: str, generation: int, *, root: Path
) -> dict[str, object] | None:
    """Read one immutable review generation without accepting its projection."""

    record = review_record_for_feature(feature_id, root=root)
    if record is None:
        return None
    generations = record.get("generations")
    if isinstance(generations, dict):
        row = generations.get(str(generation))
        return dict(row) if isinstance(row, dict) else None
    if generation == 0:
        return _generation_projection(record)
    return None


def review_callback_is_current(
    feature_id: str,
    record: dict[str, object],
    *,
    root: Path,
    snapshot: dict[str, object] | None = None,
) -> bool:
    """Fence forge observations to the generation and URL they observed."""

    current = review_record_for_feature(feature_id, root=root)
    if current is None:
        return False
    matches = (
        int(current.get("current_generation") or 0)
        == int(record.get("current_generation") or 0)
        and current.get("url") == record.get("url")
        and current.get("source_branch") == record.get("source_branch")
        and current.get("target_branch") == record.get("target_branch")
    )
    if (
        not matches
        or snapshot is None
        or int(current.get("current_generation") or 0) == 0
    ):
        return matches
    return bool(
        snapshot.get("merge_sha")
        and snapshot.get("source_revision") == current.get("source_head")
    )


def _actual_accepted_merge_identity(
    record: Mapping[str, object], snapshot: Mapping[str, object]
) -> dict[str, object] | None:
    """Return complete forge acceptance identity; never infer it from Git ancestry."""

    if snapshot.get("state") != "merged":
        return None
    observed = snapshot.get("accepted_merge_identity")
    if isinstance(observed, Mapping):
        if observed.get("available") is not True:
            return None
        identity = dict(observed)
    else:
        identity = {
            "available": True,
            "review_url": snapshot.get("url"),
            "source_branch": snapshot.get("source_branch"),
            "target_branch": snapshot.get("target_branch"),
            "source_revision": snapshot.get("source_revision"),
            "merge_sha": snapshot.get("merge_sha"),
            "observed_target_head": snapshot.get("target_revision"),
        }
    expected = {
        "review_url": record.get("url"),
        "source_branch": record.get("source_branch"),
        "target_branch": record.get("target_branch"),
        "source_revision": record.get("source_head"),
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        return None
    if any(
        not isinstance(identity.get(field), str) or not identity.get(field)
        for field in ("review_url", "source_branch", "target_branch", "source_revision")
    ):
        return None
    if any(
        not isinstance(identity.get(field), str)
        or not re.fullmatch(r"[0-9a-f]{40}", str(identity[field]))
        for field in ("source_revision", "merge_sha", "observed_target_head")
    ):
        return None
    identity["review_generation"] = int(record.get("current_generation") or 0)
    return identity


def matching_exact_result_receipt(
    record: Mapping[str, object], snapshot: Mapping[str, object], *, root: Path
) -> dict[str, object] | None:
    """Match the candidate proof using the same receipt reader as publication."""

    proof = record.get("exact_candidate_proof")
    if not isinstance(proof, Mapping):
        return None if record.get("candidate_proof_required") is True else {}
    incident_id = proof.get("incident_id")
    identity = proof.get("identity")
    fingerprint = proof.get("fingerprint")
    if not isinstance(incident_id, str) or not isinstance(identity, dict):
        return None
    from cascade.review_validation import (
        ExactValidationMaterial,
        exact_material_fingerprint,
        match_review_validation_receipt,
    )

    if (
        not isinstance(fingerprint, str)
        or exact_material_fingerprint(identity) != fingerprint
    ):
        return None
    review_identity = identity.get("review")
    candidate = identity.get("candidate")
    if not isinstance(review_identity, Mapping) or not isinstance(candidate, Mapping):
        return None
    expected_route = {
        "review_url": record.get("url"),
        "source_ref": record.get("source_branch"),
        "target_ref": record.get("target_branch"),
    }
    if any(review_identity.get(key) != value for key, value in expected_route.items()):
        return None
    if any(
        snapshot.get(observed) != record.get(stored)
        for observed, stored in (
            ("url", "url"),
            ("source_branch", "source_branch"),
            ("target_branch", "target_branch"),
        )
    ):
        return None
    if (
        candidate.get("source_sha") != snapshot.get("source_revision")
        or candidate.get("target_sha") != record.get("target_head")
    ):
        return None
    state, receipt = match_review_validation_receipt(
        incident_id,
        ExactValidationMaterial(identity, fingerprint),
        root=root,
    )
    if state != "matching_green" or not isinstance(receipt, dict):
        return None
    operation_id = proof.get("operation_id")
    if operation_id is not None and receipt.get("operation_id") != operation_id:
        return None
    return {
        "incident_id": incident_id,
        "operation_id": receipt.get("operation_id"),
        "fingerprint": fingerprint,
        "identity": identity,
    }


def record_exact_candidate_proof(
    feature_id: str,
    incident_id: str,
    operation_id: str,
    material: object,
    *,
    root: Path,
) -> bool:
    """Attach a settled publication proof to its current immutable review route."""

    identity = getattr(material, "identity", None)
    fingerprint = getattr(material, "fingerprint", None)
    if not isinstance(identity, dict) or not isinstance(fingerprint, str):
        return False
    from cascade.review_validation import match_review_validation_receipt

    state, receipt = match_review_validation_receipt(incident_id, material, root=root)
    if (
        state != "matching_green"
        or not isinstance(receipt, dict)
        or receipt.get("operation_id") != operation_id
    ):
        return False
    current = review_record_for_feature(feature_id, root=root)
    review_identity = identity.get("review")
    if not isinstance(current, dict) or not isinstance(review_identity, Mapping):
        return False
    if any(
        review_identity.get(field) != current.get(record_field)
        for field, record_field in (
            ("review_url", "url"),
            ("source_ref", "source_branch"),
            ("target_ref", "target_branch"),
        )
    ):
        return False
    _update_record(
        root,
        feature_id,
        {
            "candidate_proof_required": True,
            "exact_candidate_proof": {
                "incident_id": incident_id,
                "operation_id": operation_id,
                "fingerprint": fingerprint,
                "identity": identity,
            },
        },
    )
    return True


def _accept_current_review_generation(
    feature_id: str,
    record: dict[str, object],
    snapshot: dict[str, object],
    *,
    root: Path,
    integration_target: str | None = None,
    integration_sha: str | None = None,
) -> bool:
    if not review_callback_is_current(feature_id, record, root=root, snapshot=snapshot):
        return False
    accepted_identity = _actual_accepted_merge_identity(record, snapshot)
    exact_proof = matching_exact_result_receipt(record, snapshot, root=root)
    if accepted_identity is None or exact_proof is None:
        return False
    merge_sha = accepted_identity["merge_sha"]
    source_revision = snapshot.get("source_revision")
    _update_record(
        root,
        feature_id,
        {
            "closed": True,
            "accepted_merge_sha": merge_sha if isinstance(merge_sha, str) else None,
            "accepted_source_head": (
                source_revision
                if isinstance(source_revision, str)
                else record.get("source_head")
            ),
            "accepted_target_head": record.get("target_head"),
            "accepted_merge_identity": accepted_identity,
            "accepted_candidate_proof": exact_proof or None,
            "reconciliation_status": "accepted",
            **(
                {
                    "integration_target_branch": integration_target,
                    "stack_integration_sha": integration_sha,
                }
                if integration_target
                else {}
            ),
        },
    )
    return True


def _save(root: Path, state: dict[str, dict[str, object]]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".reviews.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


@contextmanager
def _registry_write_lock(root: Path):
    """Serialize short read-modify-write steps across worker and CLI processes."""

    lock_path = _state_path(root).with_suffix(".lock")
    with process_lock:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _update_record(
    root: Path,
    feature_id: str,
    changes: dict[str, object],
    *,
    create: bool = False,
    only_if_absent: bool = False,
) -> dict[str, object] | None:
    """Merge one feature's fields into the latest registry without losing peers."""

    with _registry_write_lock(root):
        state = _load(root)
        existing = state.get(feature_id)
        if not isinstance(existing, dict):
            if not create:
                return None
            existing = {}
        elif only_if_absent and existing:
            return dict(existing)
        updated = dict(existing)
        updated.update(changes)
        if "seen_comments" in changes:
            previous_seen = existing.get("seen_comments")
            previous_seen = previous_seen if isinstance(previous_seen, list) else []
            incoming_seen = changes["seen_comments"]
            incoming_seen = incoming_seen if isinstance(incoming_seen, list) else []
            updated["seen_comments"] = sorted(
                {str(row) for row in previous_seen}
                | {str(row) for row in incoming_seen}
            )
        generations_raw = updated.get("generations")
        current_generation = updated.get("current_generation")
        if isinstance(generations_raw, dict) and isinstance(current_generation, int):
            generations = dict(generations_raw)
            current = generations.get(str(current_generation))
            if isinstance(current, dict):
                current = dict(current)
                current.update(
                    {
                        key: value
                        for key, value in changes.items()
                        if key not in _GENERATION_CONTAINER_FIELDS
                    }
                )
                generations[str(current_generation)] = current
                updated["generations"] = generations
        if updated != existing:
            state[feature_id] = updated
            _save(root, state)
        return updated


def _store_review_generation(
    root: Path,
    feature_id: str,
    projection: dict[str, object],
    *,
    generation: int,
    action_id: str | None,
) -> dict[str, object]:
    """Atomically advance the current projection without rewriting history."""

    with _registry_write_lock(root):
        state = _load(root)
        existing = state.get(feature_id)
        base = dict(existing) if isinstance(existing, dict) else {}
        legacy_upgrade = bool(base) and not isinstance(base.get("generations"), dict)
        if legacy_upgrade:
            base = _versioned_review_record(base, generation=0, action_id=None)
        if legacy_upgrade and generation == 0 and action_id is None:
            state[feature_id] = base
            _save(root, state)
            return base
        updated = _versioned_review_record(
            {**base, **projection}, generation=generation, action_id=action_id
        )
        # ``_versioned_review_record`` seeds the new row from compatibility
        # fields. Replace it with the exact new projection; prior rows remain.
        generations = dict(updated.get("generations") or {})
        generation_row = dict(projection)
        generation_row.update(
            generation=generation,
            action_id=action_id,
            publication_action_id=action_id,
            reconciliation_status="pending",
        )
        generations[str(generation)] = generation_row
        updated.update(generation_row)
        for field in (
            "forge_acceptance",
            "stacked_acceptance",
            "integration_target_branch",
            "stack_integration_sha",
            "candidate_proof_required",
            "exact_candidate_proof",
            "accepted_merge_identity",
            "accepted_candidate_proof",
        ):
            if field not in generation_row:
                updated.pop(field, None)
        updated["generations"] = generations
        updated["current_generation"] = generation
        updated["schema_version"] = 2
        state[feature_id] = updated
        _save(root, state)
        return updated


def review_enabled(root: Path) -> bool:
    return forge_ready(locate_trunk(root))


def feature_review_pending(feature_id: str, *, root: Path) -> bool:
    """True while a completed source branch still awaits its forge merge."""

    trunk = locate_trunk(root)
    record = _load(trunk).get(feature_id)
    if record is not None:
        return not bool(record.get("closed"))
    # Closing the plan precedes publication. Treat that preparation window as
    # pending too, so a sibling cannot dispatch if normalization or MR creation
    # fails before reviews.json is written.
    if not review_enabled(trunk):
        return False
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None or not entry.path.is_dir():
        return False
    try:
        doc = read_doc(feature_id, root=entry.path)
    except NotFound:
        return False
    return doc.meta.status == "completed" and doc.meta.path.parent.name == "3_completed"


def _forge_acceptance(record: dict[str, object]) -> dict[str, object] | None:
    receipt = record.get("forge_acceptance")
    if (
        isinstance(receipt, dict)
        and receipt.get("url") == record.get("url")
        and receipt.get("target_branch") == record.get("target_branch")
        and receipt.get("generation") == int(record.get("current_generation") or 0)
        and receipt.get("merge_sha")
    ):
        return receipt
    return None


def _record_forge_acceptance(
    feature_id: str,
    record: dict[str, object],
    snapshot: dict[str, object],
    *,
    root: Path,
) -> None:
    accepted_identity = _actual_accepted_merge_identity(record, snapshot)
    exact_proof = matching_exact_result_receipt(record, snapshot, root=root)
    if accepted_identity is None or exact_proof is None:
        return
    merge_sha = accepted_identity["merge_sha"]
    source = accepted_identity["source_revision"]
    if not review_callback_is_current(feature_id, record, root=root, snapshot=snapshot):
        return
    receipt = {
        "url": record.get("url"),
        "target_branch": record.get("target_branch"),
        "generation": int(record.get("current_generation") or 0),
        "merge_sha": merge_sha,
        "source_revision": source,
        "accepted_merge_identity": accepted_identity,
        "accepted_candidate_proof": exact_proof or None,
    }
    if _forge_acceptance(record) != receipt:
        _update_record(root, feature_id, {"forge_acceptance": receipt})


def _stacked_acceptance(record: dict[str, object]) -> dict[str, object] | None:
    receipt = record.get("stacked_acceptance")
    if (
        isinstance(receipt, dict)
        and receipt.get("url") == record.get("url")
        and receipt.get("target_branch") == record.get("target_branch")
        and receipt.get("generation") == int(record.get("current_generation") or 0)
        and str(record.get("target_branch") or "").startswith("feat/")
        and receipt.get("merge_sha")
    ):
        return receipt
    return None


def _feature_review_projection(
    record: dict[str, object], state: dict[str, dict[str, object]]
) -> dict[str, object]:
    receipt = _stacked_acceptance(record)
    result = {
        "state": "merged"
        if record.get("closed")
        else "awaiting_integration"
        if receipt
        else "awaiting_closeout"
        if _forge_acceptance(record)
        else "awaiting_review",
        "url": str(record.get("url") or ""),
        "number": record.get("number"),
        "draft": bool(record.get("draft", False)),
    }
    if receipt and not record.get("closed"):
        predecessor = str(receipt["target_branch"]).removeprefix("feat/")
        result["integration_feature_id"] = predecessor
        upstream = state.get(predecessor, {})
        result["integration_review_url"] = str(upstream.get("url") or "")
    if result["state"] == "awaiting_closeout" and isinstance(
        record.get("closeout_blocker"), dict
    ):
        result["closeout_blocker"] = record["closeout_blocker"]
    return result


FeatureDeliveryPhase = Literal[
    "implementation_ready",
    "review_pending",
    "repair_requested",
    "repair_in_progress",
    "merge_verification_pending",
    "verified_integrated",
    "terminal_cancelled",
    "terminal_closed",
]


def _accepted_current_generation(record: dict[str, object]) -> bool:
    """Require the exact accepted heads of the current compatibility row."""

    accepted = bool(
        record.get("closed") is True
        and record.get("reconciliation_status") == "accepted"
        and record.get("accepted_merge_sha")
        and record.get("accepted_source_head") == record.get("source_head")
        and record.get("accepted_target_head") == record.get("target_head")
    )
    if not accepted:
        return False
    generations = record.get("generations")
    if not isinstance(generations, dict):
        return int(record.get("current_generation") or 0) == 0
    current = generations.get(str(int(record.get("current_generation") or 0)))
    if not isinstance(current, dict):
        return False
    fenced_fields = (
        "url",
        "source_branch",
        "target_branch",
        "source_head",
        "target_head",
        "accepted_merge_sha",
        "accepted_source_head",
        "accepted_target_head",
        "reconciliation_status",
    )
    return all(current.get(field) == record.get(field) for field in fenced_fields)


def _feature_completion_recorded(
    feature_id: str, parent_id: str | None, root: Path
) -> bool:
    if not parent_id:
        return False
    events, _ = read_events(parent_id, 0, root=root)
    return any(
        event.type == "FeatureCompleted"
        and event.payload.get("feature_id") == feature_id
        for event in events
    )


def _git_ref_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Read local Git ancestry without fetching or changing refs."""

    try:
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", ancestor, descendant],
                cwd=root,
                capture_output=True,
                timeout=5,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _supported_terminal_phase(
    meta, record: dict[str, object] | None, board
) -> FeatureDeliveryPhase | None:
    """Recognize only existing, explicit terminal evidence."""

    if (
        meta is not None
        and meta.status == "cancelled"
        and meta.path.parent.name == "3_completed"
        and meta.cancellation_step == "complete"
        and meta.cancellation_error is None
        and meta.cancelled_at is not None
        and meta.cancellation_reason
    ):
        parent = board.by_id.get(meta.parent) if meta.parent else None
        feedback = (
            [item for item in parent.cancellation_feedback if item.child_id == meta.id]
            if parent is not None
            else []
        )
        if len(feedback) == 1:
            disposition = feedback[0]
            if (
                disposition.child_tier == "feature"
                and disposition.parent_id == parent.id
                and disposition.cancelled_at == meta.cancelled_at
                and disposition.reason == meta.cancellation_reason
                and disposition.disposition == "continue_reduced_scope"
                and disposition.resolved_at is not None
            ):
                return "terminal_cancelled"
    disposition = record.get("terminal_disposition") if record else None
    generations = record.get("generations") if record else None
    if isinstance(generations, dict):
        current = generations.get(str(int(record.get("current_generation") or 0)))
        if (
            not isinstance(current, dict)
            or current.get("terminal_disposition") != disposition
        ):
            disposition = None
    if disposition in {"closed", "terminal_closed"}:
        return "terminal_closed"
    if disposition in {"cancelled", "terminal_cancelled"}:
        return "terminal_cancelled"
    return None


def _delivery_projection(
    feature_id: str,
    *,
    trunk: Path,
    board,
    record: dict[str, object] | None,
    repair: dict[str, object] | None,
    reviews_enabled: bool,
) -> dict[str, object]:
    """Derive one Feature delivery row from already-persisted local evidence."""

    meta = board.by_id.get(feature_id)
    parent_id = (
        str(meta.parent) if meta is not None and meta.parent is not None else None
    )
    record_generation = int(record.get("current_generation") or 0) if record else 0
    repair_generation = int(repair.get("generation") or 0) if repair else 0
    generation = max(record_generation, repair_generation)
    review_url = str(record.get("url") or "") if record else ""
    completed_event = _feature_completion_recorded(feature_id, parent_id, trunk)
    terminal = _supported_terminal_phase(meta, record, board)

    phase: FeatureDeliveryPhase
    evidence_status: str
    blocker: str | None
    next_prerequisite: str | None

    if terminal is not None:
        phase = terminal
        evidence_status = "explicit_terminal_disposition"
        blocker = None
        next_prerequisite = None
    else:
        repair_phase = str(repair.get("phase") or "") if repair else ""
        exact_generation = bool(
            record
            and record_generation == generation
            and _accepted_current_generation(record)
        )
        target_branch = f"epic/{parent_id}" if parent_id else ""
        integration_anchor = (
            str(
                record.get("stack_integration_sha")
                or record.get("accepted_merge_sha")
                or ""
            )
            if record
            else ""
        )
        target_integrated = bool(
            exact_generation
            and target_branch
            and integration_anchor
            and _git_ref_ancestor(trunk, integration_anchor, target_branch)
        )
        local_integrated = bool(
            record is None
            and parent_id
            and _git_ref_ancestor(
                trunk, integration_branch("feature", feature_id), target_branch
            )
        )

        if (
            target_integrated
            or (record is None and not reviews_enabled and local_integrated)
        ) and completed_event:
            phase = "verified_integrated"
            evidence_status = (
                "accepted_current_generation"
                if target_integrated
                else "local_integration"
            )
            blocker = None
            next_prerequisite = None
        elif target_integrated:
            # The accepted repair has left the publication phase even when its
            # repair receipt is still awaiting Boss's terminal acknowledgement.
            # Boss owns the missing completion event, so expose that exact last
            # prerequisite instead of projecting the older delivery phase.
            phase = "merge_verification_pending"
            evidence_status = "accepted_current_generation"
            blocker = "completion_event_missing"
            next_prerequisite = "record_feature_completion"
        elif repair and repair_phase in {"prepared", "authority_recorded"}:
            phase = "repair_requested"
            evidence_status = "repair_admitted"
            blocker = "repair_not_started"
            next_prerequisite = str(
                repair.get("next_action") or "resume_admitted_repair"
            )
        elif repair and (
            record is None
            or record_generation != repair_generation
            or repair_phase in {"parent_enabled", "delivery_pending"}
        ):
            phase = "repair_in_progress"
            evidence_status = "repair_generation_active"
            blocker = "repair_delivery_incomplete"
            next_prerequisite = str(
                repair.get("next_action") or "publish_repair_review"
            )
        elif (
            exact_generation
            or _forge_acceptance(record or {})
            or _stacked_acceptance(record or {})
        ):
            phase = "merge_verification_pending"
            evidence_status = (
                "accepted_current_generation"
                if exact_generation
                else "forge_acceptance_observed"
            )
            blocker = (
                "completion_event_missing"
                if target_integrated
                else "intended_target_not_verified"
            )
            next_prerequisite = (
                "record_feature_completion"
                if target_integrated
                else "verify_intended_target_integration"
            )
        elif record is not None and (
            record.get("closed") is True
            or str(record.get("state") or "").lower() in {"closed", "merged"}
        ):
            phase = "merge_verification_pending"
            if record_generation == 0 and not record.get("accepted_merge_sha"):
                evidence_status = "legacy_unverified"
            else:
                evidence_status = "closed_unmerged"
            blocker = "accepted_current_generation_missing"
            next_prerequisite = "restore_review_evidence_or_record_terminal_disposition"
        elif record is not None:
            phase = "review_pending"
            evidence_status = "open" if review_url else "unknown_review_evidence"
            blocker = (
                "review_acceptance_pending" if review_url else "review_evidence_missing"
            )
            next_prerequisite = (
                "await_current_review_acceptance" if review_url else "publish_review"
            )
        else:
            children_complete = bool(meta is not None) and all(
                child_id in board.by_id
                and board.by_id[child_id].status == "completed"
                and board.by_id[child_id].path.parent.name == "3_completed"
                for child_id in meta.children
            )
            source_completed = bool(
                meta is not None
                and meta.status == "completed"
                and meta.path.parent.name == "3_completed"
            )
            phase = "implementation_ready"
            if source_completed and children_complete:
                evidence_status = "review_evidence_missing"
                blocker = (
                    "review_not_published"
                    if reviews_enabled
                    else "local_integration_pending"
                )
                next_prerequisite = (
                    "publish_review" if reviews_enabled else "integrate_locally"
                )
            else:
                evidence_status = "implementation_incomplete"
                blocker = "implementation_not_ready"
                next_prerequisite = "complete_child_delivery"

    actionable = bool(
        repair
        and str(repair.get("phase") or "")
        in {"prepared", "authority_recorded", "parent_enabled", "delivery_pending"}
    )
    return {
        "feature_id": feature_id,
        "accountable_owner": f"feature_team:{feature_id}",
        "phase": phase,
        "review_url": review_url,
        "generation": generation,
        # The active repair generation can advance before its review receipt.
        # Keep publication evidence separate from the projected obligation.
        "published_generation": record_generation if record is not None else None,
        "evidence_status": evidence_status,
        "blocker": blocker,
        "next_prerequisite": next_prerequisite,
        "actionable": actionable,
    }


_REPAIR_ACTIVE_PHASES = frozenset(
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


def _bounded_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized[:limit] if normalized else None


def _review_evidence_projection(
    record: Mapping[str, object], repair: Mapping[str, object] | None
) -> dict[str, object]:
    """Expose bounded persisted health facts without consulting forge authority."""

    source = "review_registry"
    health = record.get("review_health")
    policy = record.get("required_check_policy")
    results = record.get("required_check_results")
    feedback = record.get("review_feedback")
    observed_at = record.get("review_observed_at") or record.get("observed_at")
    bounded_payload: object = {
        "review_health": health,
        "required_check_policy": policy,
        "required_check_results": results,
        "review_feedback": feedback,
        "review_observed_at": observed_at,
    }

    if repair is not None:
        postcheck = repair.get("verification_postcheck")
        request_evidence = repair.get("request_evidence")
        request_health = (
            request_evidence.get("review_health")
            if isinstance(request_evidence, Mapping)
            else None
        )
        observation = (
            request_health.get("observation")
            if isinstance(request_health, Mapping)
            else None
        )
        if isinstance(postcheck, Mapping):
            source = "verification_postcheck"
            bounded_payload = postcheck
            health = {"state": "green"} if postcheck.get("verified") else health
            policy = postcheck.get("required_check_policy") or policy
            results = postcheck.get("required_check_results") or results
            observed_at = postcheck.get("verified_at") or repair.get("verified_at")
        elif isinstance(observation, Mapping):
            source = "repair_request"
            bounded_payload = observation
            health = {
                "state": observation.get("health_state"),
                "reason": observation.get("reason"),
            }
            blocker = observation.get("blocker")
            if isinstance(blocker, Mapping):
                policy = blocker.get("policy") or policy
                checks = blocker.get("checks")
                if checks is not None:
                    results = {"available": True, "checks": checks}
            observed_at = (
                request_health.get("observed_at")
                if isinstance(request_health, Mapping)
                else observed_at
            )

    health = health if isinstance(health, Mapping) else {}
    policy = policy if isinstance(policy, Mapping) else {}
    results = results if isinstance(results, Mapping) else {}
    feedback = feedback if isinstance(feedback, Mapping) else {}
    health_state = _bounded_text(health.get("state")) or "unknown"
    health_reason = _bounded_text(health.get("reason"))

    raw_checks = results.get("checks")
    check_rows: list[dict[str, object]] = []
    evidence_unavailable = False
    omitted = 0
    try:
        if not _review_evidence_payload_within_bound(bounded_payload):
            raise ValueError("review evidence exceeds the normalized byte limit")
        health_checks = health.get("checks")
        if health_checks is not None:
            if not isinstance(health_checks, list):
                raise ValueError("health checks must be a list")
            for name in health_checks:
                _review_evidence_name(name)
        required = policy.get("required")
        if required is not None:
            if not isinstance(required, list):
                raise ValueError("required checks must be a list")
            for name in required:
                _review_evidence_name(name)
        _review_evidence_generation(results.get("generation"))
        raw_statuses = results.get("statuses")
        if isinstance(raw_statuses, Mapping):
            for name, status in raw_statuses.items():
                _review_evidence_name(name)
                if not isinstance(status, str):
                    raise ValueError("check status must be a string")
        elif raw_statuses is not None:
            raise ValueError("check statuses must be a mapping")
        if isinstance(raw_checks, Mapping):
            names = sorted(_review_evidence_name(name) for name in raw_checks)
            normalized_generations = {}
            for name, raw_check in raw_checks.items():
                if not isinstance(raw_check, Mapping):
                    raise ValueError("check result must be a mapping")
                normalized_generations[name] = _review_evidence_generation(
                    raw_check.get("generation")
                )
                if raw_check.get("status") is not None and not isinstance(
                    raw_check.get("status"), str
                ):
                    raise ValueError("check result status must be a string")
                if raw_check.get("conclusion") is not None and not isinstance(
                    raw_check.get("conclusion"), str
                ):
                    raise ValueError("check result conclusion must be a string")
            omitted = max(0, len(names) - _REVIEW_EVIDENCE_MAX_CHECK_ROWS)
            for name in names[:_REVIEW_EVIDENCE_MAX_CHECK_ROWS]:
                check = raw_checks[name]
                check = check if isinstance(check, Mapping) else {}
                check_rows.append(
                    {
                        "name": name,
                        "status": _bounded_text(
                            check.get("status") or check.get("conclusion"), limit=40
                        )
                        or "unknown",
                        "generation": normalized_generations[name],
                        "observed_at": _bounded_text(
                            check.get("observed_at"), limit=64
                        ),
                    }
                )
        elif isinstance(raw_checks, list):
            names = [_review_evidence_name(name) for name in raw_checks]
            omitted = max(0, len(names) - _REVIEW_EVIDENCE_MAX_CHECK_ROWS)
            check_rows = [
                {"name": name, "status": "unknown"}
                for name in names[:_REVIEW_EVIDENCE_MAX_CHECK_ROWS]
            ]
        elif raw_checks is not None:
            raise ValueError("check results must be a mapping or list")
        persisted_omitted = results.get("checks_omitted")
        if persisted_omitted is not None:
            normalized_omitted = _review_evidence_generation(persisted_omitted)
            if type(normalized_omitted) is not int or normalized_omitted < 0:
                raise ValueError("omitted check count must be a non-negative integer")
            omitted = max(omitted, normalized_omitted)
        if health_state == "green" and (
            policy.get("available") is not True
            or results.get("available") is not True
        ):
            raise ValueError("green evidence requires available policy and results")
    except (TypeError, ValueError, UnicodeError):
        evidence_unavailable = True
        check_rows = []
        omitted = 0

    if evidence_unavailable:
        health_state = "unavailable"
        health_reason = _REVIEW_EVIDENCE_UNAVAILABLE
        policy = {"available": False}
        results = {"available": False}

    stale = health_state == "conflict_or_moving_target" or bool(
        health_reason and "stale" in health_reason
    )
    observed = _bounded_text(observed_at, limit=64)
    freshness = (
        "unknown"
        if evidence_unavailable
        else "stale"
        if stale
        else "current"
        if observed
        else "unknown"
    )
    policy_status = (
        "available"
        if policy.get("available") is True
        else "unavailable"
        if policy.get("available") is False
        else "unknown"
    )
    results_status = (
        "available"
        if results.get("available") is True
        else "unavailable"
        if results.get("available") is False
        else "unknown"
    )
    feedback_status = (
        "available"
        if feedback.get("available") is True
        else "unavailable"
        if feedback.get("available") is False
        else "unknown"
    )
    if health_state == "actionable_human_feedback":
        feedback_status = "available"

    return {
        "source": source,
        "health_state": health_state,
        "health_reason": health_reason,
        "ci": {
            "policy_status": policy_status,
            "results_status": results_status,
            "checks": check_rows,
            "truncated": omitted > 0,
            "omitted": omitted,
        },
        "feedback": {
            "status": feedback_status,
            "approval_state": _bounded_text(feedback.get("approval_state"), limit=40),
            "actionable": health_state == "actionable_human_feedback"
            or feedback.get("actionable") is True,
        },
        "observed_at": observed,
        "freshness": freshness,
        "next_prerequisite": (
            "refresh_review_observation" if evidence_unavailable else None
        ),
    }


def _repair_projection(repair: Mapping[str, object] | None) -> dict[str, object]:
    if repair is None:
        return {
            "request_id": None,
            "action_id": None,
            "generation": 0,
            "phase": None,
            "requested": False,
            "admitted": False,
            "acknowledged": False,
            "executing": False,
            "verified": False,
            "waiting": False,
            "refused": False,
            "next_prerequisite": None,
        }
    phase = str(repair.get("phase") or "")
    generation = repair.get("generation")
    generation = generation if type(generation) is int and generation >= 0 else 0
    return {
        "request_id": _bounded_text(repair.get("request_id"), limit=160),
        "action_id": _bounded_text(repair.get("action_id"), limit=160),
        "generation": generation,
        "phase": phase or None,
        "requested": True,
        "admitted": phase in _REPAIR_ACTIVE_PHASES or phase == "verified",
        "acknowledged": True,
        "executing": phase
        in {"delivery_pending", "review_pending", "integration_pending"},
        "verified": phase == "verified",
        "waiting": phase == "waiting",
        "refused": phase == "refused",
        "next_prerequisite": _bounded_text(repair.get("next_action"), limit=160),
    }


def _accountable_review_projection(
    feature_id: str,
    record: dict[str, object],
    *,
    meta: WorkMeta | None,
    delivery: dict[str, object],
    repair: dict[str, object] | None,
    state: dict[str, dict[str, object]],
) -> dict[str, object]:
    projection = _feature_review_projection(record, state)
    repair_view = _repair_projection(repair)
    evidence = _review_evidence_projection(record, repair)
    epic_id = _review_target_epic(record) or (str(meta.parent) if meta and meta.parent else None)
    next_prerequisite = (
        evidence.get("next_prerequisite")
        or repair_view.get("next_prerequisite")
        or delivery.get("next_prerequisite")
    )
    if evidence.get("health_state") == "unavailable" and repair_view.get("verified"):
        repair_view = {
            **repair_view,
            "verified": False,
            "waiting": True,
            "next_prerequisite": "refresh_review_observation",
        }
    projection.update(
        {
            "original_review": {
                "url": str(record.get("url") or ""),
                "number": record.get("number"),
            },
            "accountable_feature_id": feature_id,
            "accountable_epic_id": epic_id,
            # Publishing the original review is durable evidence that its
            # implementation reached review, even when a repair temporarily
            # moves the Feature document back to the active column.
            "implementation_status": "completed",
            "implementation_complete": True,
            "work_status": meta.status if meta is not None else "unknown",
            "delivery_status": delivery.get("phase"),
            "delivery": delivery,
            "evidence": evidence,
            "repair": repair_view,
            "repair_identity": {
                "review_url": _bounded_text(record.get("url"), limit=2048),
                "review_forge": _bounded_text(record.get("forge"), limit=80),
                "source_ref": _bounded_text(record.get("source_branch"), limit=256),
                "target_ref": _bounded_text(record.get("target_branch"), limit=256),
                "observed_source_head": _bounded_text(
                    record.get("source_head"), limit=160
                ),
                "observed_target_head": _bounded_text(
                    record.get("target_head"), limit=160
                ),
                "observed_review_generation": int(
                    record.get("current_generation") or 0
                ),
            },
            "next_prerequisite": next_prerequisite,
        }
    )
    return projection


def feature_delivery_view(feature_id: str, *, root: Path) -> dict[str, object]:
    """Return the read-only delivery lifecycle for one Feature."""

    return feature_delivery_views([feature_id], root=root)[feature_id]


def feature_delivery_satisfies_integration(
    delivery: Mapping[str, object],
) -> bool:
    """True only when current evidence permits integration-required execution."""

    return delivery.get("phase") in {
        "verified_integrated",
        "terminal_cancelled",
        "terminal_closed",
    }


def feature_delivery_views(
    feature_ids: list[str] | tuple[str, ...] | set[str],
    *,
    root: Path,
    board_snapshot: BoardIndex | None = None,
) -> dict[str, dict[str, object]]:
    """Project delivery rows while sharing one review and board snapshot."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    from cascade.feature.repair import current_feature_repair_record, current_feature_repair_records
    from cascade.workspace.integration_worktree import merged_board_readonly

    ids = set(feature_ids)
    board = board_snapshot or merged_board_readonly(trunk)
    # Single-owner admission remains a fresh check. Multi-row projections read
    # the atomic action sidecar once, not once per Feature.
    if len(ids) == 1:
        work_id = next(iter(ids))
        repairs = {work_id: current_feature_repair_record(work_id, root=trunk)}
    else:
        repairs = current_feature_repair_records(ids, root=trunk)
    reviews_enabled = review_enabled(trunk)
    return {
        feature_id: _delivery_projection(
            feature_id,
            trunk=trunk,
            board=board,
            record=state.get(feature_id),
            repair=repairs.get(feature_id),
            reviews_enabled=reviews_enabled,
        )
        for feature_id in feature_ids
    }


def feature_review_view(feature_id: str, *, root: Path) -> dict[str, object] | None:
    """Return operator-facing review state without polling the forge."""

    return feature_review_views([feature_id], root=root)[feature_id]


def feature_review_views(
    feature_ids: list[str] | tuple[str, ...] | set[str],
    *,
    root: Path,
    board_snapshot: BoardIndex | None = None,
) -> dict[str, dict[str, object] | None]:
    """Build multiple operator review views with one registry/sidecar load."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    ids = list(feature_ids)
    from cascade.feature.repair import latest_feature_repair_records
    from cascade.workspace.integration_worktree import merged_board_readonly

    board = board_snapshot or merged_board_readonly(trunk)
    repairs = latest_feature_repair_records(ids, root=trunk)
    reviews_enabled = review_enabled(trunk)
    missing = [feature_id for feature_id in ids if feature_id not in state]
    enabled = bool(missing) and reviews_enabled
    entries = {
        entry.work_id: entry
        for entry in load_registry(trunk)
        if enabled and entry.kind == "feature" and entry.work_id in missing
    }
    views: dict[str, dict[str, object] | None] = {}
    for feature_id in ids:
        record = state.get(feature_id)
        if record is not None:
            repair = repairs.get(feature_id)
            delivery = _delivery_projection(
                feature_id,
                trunk=trunk,
                board=board,
                record=record,
                repair=repair,
                reviews_enabled=reviews_enabled,
            )
            views[feature_id] = _accountable_review_projection(
                feature_id,
                record,
                meta=board.by_id.get(feature_id),
                delivery=delivery,
                repair=repair,
                state=state,
            )
            continue
        entry = entries.get(feature_id)
        pending = False
        if entry is not None and entry.path.is_dir():
            try:
                doc = read_doc(feature_id, root=entry.path)
            except NotFound:
                pass
            else:
                pending = (
                    doc.meta.status == "completed"
                    and doc.meta.path.parent.name == "3_completed"
                )
        views[feature_id] = (
            {
                "state": "preparing_review",
                "url": "",
                "number": None,
                "draft": False,
            }
            if pending
            else None
        )
    return views


def epic_has_pending_feature_review(epic_id: str, *, root: Path) -> bool:
    """True when any child feature is prepared for or awaiting forge review."""

    trunk = locate_trunk(root)
    from cascade.workspace.integration_worktree import merged_board

    for meta in merged_board(trunk).by_id.values():
        if meta.tier != "feature" or meta.parent != epic_id:
            continue
        if feature_review_pending(meta.id, root=trunk):
            return True
    return False


def ensure_epic_review(epic_id: str, *, root: Path) -> MergeRequest | None:
    """Publish a completed epic line to the product trunk for human review."""

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    from cascade.workspace.trunk import resolve_product_trunk

    entry = get_integration_worktree(trunk, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    doc = read_doc(epic_id, root=entry.path)
    if doc.meta.tier != "epic":
        raise NotFound(epic_id)
    if doc.meta.status == "active" and doc.meta.path.parent.name == "2_active":
        move_doc(epic_id, "completed", root=entry.path)
    elif doc.meta.status != "completed" or doc.meta.path.parent.name != "3_completed":
        raise GitError(f"{epic_id} must be active or completed before review")
    source = integration_branch("epic", epic_id)
    target = resolve_product_trunk(trunk)
    _restore_unrelated_specs_for_epic_review(entry.path, trunk, epic_id)
    push_branch(entry.path, source)
    existing = find_merge_request(
        entry.path, source_branch=source, target_branch=target
    )
    if existing is not None:
        persist_epic_review_snapshot(
            epic_id,
            EpicReviewSnapshot(
                stage="implementation_review_pending",
                review_url=existing.url,
                source_branch=existing.source_branch,
                target_branch=existing.target_branch,
                forge_state="open",
            ),
            root=trunk,
        )
        return existing
    created = create_merge_request(
        entry.path,
        title=f"{epic_id}: {doc.meta.title}",
        body=f"Delivers `{epic_id}` to `{target}`. Review the completed epic before merging.",
        source_branch=source,
        target_branch=target,
        draft=False,
    )
    persist_epic_review_snapshot(
        epic_id,
        EpicReviewSnapshot(
            stage="implementation_review_pending",
            review_url=created.url,
            source_branch=created.source_branch,
            target_branch=created.target_branch,
            forge_state="open",
        ),
        root=trunk,
    )
    return created


def _restore_unrelated_specs_for_epic_review(
    epic_root: Path, trunk: Path, epic_id: str
) -> None:
    """Keep activation's spec scrub from deleting remote trunk's other specs."""

    from cascade.workspace.closeout import create_verified_trunk_workspace

    def git(args: list[str], cwd: Path) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            raise GitError((result.stderr or result.stdout).strip() or "git failed")
        return result.stdout.strip()

    if git(["status", "--porcelain", "--untracked-files=no"], epic_root):
        raise GitError(f"epic worktree has uncommitted changes: {epic_id}")
    with create_verified_trunk_workspace(trunk) as workspace:
        changed = git(
            [
                "diff",
                "--name-only",
                workspace.revision,
                "HEAD",
                "--",
                "docs/features",
                "docs/tasks",
            ],
            epic_root,
        ).splitlines()
        number = epic_id.removeprefix("epic_")
        restore = [
            path
            for path in changed
            if not Path(path).name.startswith((f"feat_{number}_", f"task_{number}_"))
            and (workspace.path / path).is_file()
        ]
        if not restore:
            return
        git(
            [
                "restore",
                f"--source={workspace.revision}",
                "--staged",
                "--worktree",
                "--",
                *restore,
            ],
            epic_root,
        )
        git(
            [
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-m",
                f"docs: preserve unrelated specs for {epic_id} review",
                "--",
                *restore,
            ],
            epic_root,
        )


def ensure_feature_review(feature_id: str, *, root: Path) -> MergeRequest | None:
    """Push a completed feature line and open one MR to its epic line."""

    trunk = locate_trunk(root)
    if not review_enabled(trunk):
        return None
    state = _load(trunk)
    existing = state.get(feature_id)
    from cascade.feature.repair import current_feature_repair_record

    repair = current_feature_repair_record(feature_id, root=trunk)
    generation = int(repair.get("generation") or 0) if repair else 0
    action_id = str(repair.get("action_id")) if repair else None
    existing_generation = (
        int(existing.get("current_generation") or 0) if existing else None
    )
    if existing and existing_generation == generation:
        if "schema_version" not in existing:
            existing = _store_review_generation(
                trunk,
                feature_id,
                _generation_projection(existing),
                generation=generation,
                action_id=action_id,
            )
        mr = _record_to_mr(existing)
        if generation > 0:
            if repair and repair.get("repair_route") == "open_review":
                _require_open_review_repair_identity(repair, existing, mr)
            snapshot = merge_request_snapshot(trunk, mr)
            if repair and repair.get("repair_route") == "open_review":
                _require_open_review_repair_identity(
                    repair, existing, mr, snapshot=snapshot
                )
            _require_repair_review_route(existing, snapshot, mr)
            if snapshot.get("state") not in {"open", "opened"}:
                if repair and repair.get("repair_route") == "open_review":
                    raise GitError("scoped repair review is no longer open")
                if snapshot.get("state") == "merged":
                    return mr
                raise GitError("current repair review is not open or merged")
        _ensure_opened_toast(feature_id, mr, existing, root=trunk)
        return mr
    entry = get_integration_worktree(trunk, "feature", feature_id)
    if entry is None:
        raise GitError(f"feature worktree missing: {feature_id}")
    if repair:
        # A validated Task cut from the superseded completed generation can
        # carry that old parent path back onto the repaired Feature branch.
        # Normalize the exact paths named by the durable repair receipt before
        # pinning and publishing the source revision.
        from cascade.boss.merge import _remove_superseded_feature_copy

        _remove_superseded_feature_copy(entry.path, feature_id, trunk)
    from cascade.board.context import get_project_context

    project = get_project_context()
    planning_root = (
        project.tracking.root
        if project is not None
        and project.target.root.resolve() != project.tracking.root.resolve()
        and trunk.resolve() == project.target.root.resolve()
        else entry.path
    )
    doc = read_doc(feature_id, root=planning_root)
    if doc.meta.tier != "feature" or not doc.meta.parent:
        raise NotFound(feature_id)
    ready_for_review = (
        doc.meta.status == "completed" and doc.meta.path.parent.name == "3_completed"
    )
    if not ready_for_review:
        if doc.meta.status != "active" or doc.meta.path.parent.name != "2_active":
            raise GitError(
                f"{feature_id} must be completed on its source branch before review"
            )
        from cascade.boss.rollup import _rollup_gates_pass

        if not _rollup_gates_pass(feature_id, doc.body, merged_board(trunk), trunk):
            raise GitError(f"{feature_id} is not ready for review publication")
    source = integration_branch("feature", feature_id)
    from cascade.stacked_dispatch import review_target_branch

    target = review_target_branch(feature_id, doc.meta.parent, root=trunk)
    # The target must exist remotely for a stacked feature MR.
    epic_entry = get_integration_worktree(trunk, "epic", doc.meta.parent)
    if epic_entry is None:
        raise GitError(f"epic worktree missing: {doc.meta.parent}")
    from cascade.feature.publication import prepare_feature_publication

    prior: dict[str, object] | None = None
    reuse: MergeRequest | None = None
    route = "initial" if existing is None else "follow_up"
    if repair and repair.get("repair_route") == "open_review" and existing is None:
        raise GitError("scoped repair requires its recorded original review")
    if existing is not None:
        prior = _generation_projection(existing)
        prior_mr = _record_to_mr(prior)
        if repair and repair.get("repair_route") == "open_review":
            _require_open_review_repair_identity(repair, existing, prior_mr)
        snapshot = merge_request_snapshot(trunk, prior_mr)
        if repair and repair.get("repair_route") == "open_review":
            _require_open_review_repair_identity(
                repair, existing, prior_mr, snapshot=snapshot
            )
        _require_repair_review_route(prior, snapshot, prior_mr, intended_target=target)
        state_name = snapshot.get("state")
        if state_name in {"open", "opened"}:
            reuse = prior_mr
            route = "refresh"
        elif repair and repair.get("repair_route") == "open_review":
            raise GitError("scoped repair review is no longer open")
        elif state_name != "merged":
            raise GitError("historical review state is unknown or conflicting")

    publication = prepare_feature_publication(feature_id, root=trunk)
    push_branch(epic_entry.path, target)
    remote_lease_sha = getattr(publication, "remote_lease_sha", None)
    if remote_lease_sha is not None:
        push_branch(entry.path, source, force_with_lease=remote_lease_sha)
    else:
        push_branch(entry.path, source)
    found = (
        find_merge_request(entry.path, source_branch=source, target_branch=target)
        if reuse is None
        else None
    )
    mr = reuse or found
    if mr is None:
        mr = create_merge_request(
            entry.path,
            title=f"{feature_id}: {doc.meta.title}",
            body=(
                f"Implements `{feature_id}` for `{doc.meta.parent}`. This review is managed by "
                "Cascade; review comments are delivered to the Feature Team."
            ),
            source_branch=source,
            target_branch=target,
            draft=False,
        )
    projection = {
        "url": mr.url,
        "number": mr.number,
        "forge": mr.forge,
        "source_branch": source,
        "target_branch": target,
        "draft": False,
        "seen_comments": [],
        "toast_notified": False,
        "source_head": head_sha(entry.path),
        "target_head": head_sha(epic_entry.path),
        "accepted_merge_sha": None,
        "closed": False,
        "route": route,
        "previous_generation": existing_generation if existing is not None else None,
        "previous_review_url": prior.get("url") if prior is not None else None,
    }
    if found is not None:
        # A prior process may have published the exact ref and opened the
        # review before it could persist this generation. Re-read both forge
        # heads before converting that remote effect into a local receipt;
        # finding a route-shaped review is not authoritative evidence that its
        # source and target still match this publication attempt.
        snapshot = merge_request_snapshot(trunk, found)
        _require_repair_review_route(projection, snapshot, found)
        if snapshot.get("state") not in {"open", "opened"}:
            raise GitError("recovered review is not open")
        if snapshot.get("target_revision") != projection["target_head"]:
            raise GitError("recovered review target changed before receipt persistence")
    record = _store_review_generation(
        trunk,
        feature_id,
        projection,
        generation=generation,
        action_id=action_id,
    )
    recorded_mr = _record_to_mr(record)
    _ensure_opened_toast(feature_id, recorded_mr, record, root=trunk)
    return mr if recorded_mr.url == mr.url else recorded_mr


def _require_repair_review_route(
    record: dict[str, object],
    snapshot: dict[str, object],
    mr: MergeRequest,
    *,
    intended_target: str | None = None,
) -> None:
    """Fail closed unless fresh forge facts confirm the recorded review route."""

    target = intended_target or str(record.get("target_branch") or "")
    observed_target = str(snapshot.get("target_branch") or "")
    observed_source = str(snapshot.get("source_branch") or "")
    expected_source_head = str(record.get("source_head") or "")
    observed_source_head = str(snapshot.get("source_revision") or "")
    if (
        not target
        or not expected_source_head
        or mr.target_branch != target
        or record.get("source_branch") != mr.source_branch
        or record.get("target_branch") != mr.target_branch
        or observed_source != mr.source_branch
        or observed_target != target
        or observed_source_head != expected_source_head
        or snapshot.get("url") != mr.url
    ):
        raise GitError("review route conflicts with authoritative forge facts")


def _require_open_review_repair_identity(
    repair: dict[str, object],
    record: dict[str, object],
    mr: MergeRequest,
    *,
    snapshot: dict[str, object] | None = None,
) -> None:
    """Bind scoped publication to the exact review admitted for repair.

    Before the first refresh the registry still projects the observed review
    generation and heads.  After checkpointing it projects the repair
    generation and newly pushed source head, so replay instead joins through
    the durable publication action ID.  Both cases retain the same review URL,
    forge, and source/target route.
    """

    repair_generation = int(repair.get("generation") or 0)
    record_generation = int(record.get("current_generation") or 0)
    expected = {
        "url": repair.get("review_url"),
        "forge": repair.get("review_forge"),
        "source_branch": repair.get("source_ref"),
        "target_branch": repair.get("target_ref"),
    }
    actual = {
        "url": record.get("url"),
        "forge": record.get("forge"),
        "source_branch": record.get("source_branch"),
        "target_branch": record.get("target_branch"),
    }
    if expected != actual or any(value in {None, ""} for value in expected.values()):
        raise GitError("scoped repair review identity changed after admission")
    if (
        mr.url != expected["url"]
        or mr.forge != expected["forge"]
        or mr.source_branch != expected["source_branch"]
        or mr.target_branch != expected["target_branch"]
    ):
        raise GitError("scoped repair review identity changed after admission")
    if snapshot is not None and snapshot.get("target_revision") != record.get(
        "target_head"
    ):
        raise GitError("scoped repair review target head changed")
    if record_generation == repair_generation:
        if record.get("action_id") != repair.get("action_id"):
            raise GitError("scoped repair publication action changed")
        return
    observed_generation = repair.get("review_generation")
    if (
        type(observed_generation) is not int
        or record_generation != observed_generation
        or record.get("source_head") != repair.get("source_head")
        or record.get("target_head") != repair.get("target_head")
    ):
        raise GitError("scoped repair review observation is stale")


def _ensure_opened_toast(
    feature_id: str,
    mr: MergeRequest,
    record: dict[str, object],
    *,
    root: Path,
) -> None:
    """Deliver the linked review notification at least once across restarts."""

    if record.get("toast_notified") is True:
        return
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "feature_review_opened",
                "id": feature_id,
                "url": mr.url,
                "message": f"Review opened for {feature_id}",
            },
            dest="war_room",
        ),
        root=root,
    )
    _update_record(root, feature_id, {"toast_notified": True})


def reconcile_feature_review_completions(root: Path) -> list[str]:
    """Finalize merged feature reviews from durable registry state; idempotent."""

    trunk = locate_trunk(root)
    state = _load(trunk)
    # Queue retention is not durable completion evidence: terminal Epic feeds
    # are pruned. Inspect the operator checkout once, without preferring a
    # completed source worktree over an incomplete target copy.
    trunk_board = list_board(trunk)
    source_board = None
    finalized: list[str] = []
    from cascade.boss.rollup import feature_completed_recorded, try_complete_feature
    from cascade.stacked_review_recovery import (
        persist_if_stacked_review_integration_gap,
    )

    for feature_id, record in list(state.items()):
        epic_id = _review_target_epic(record)
        if record.get("closed") and _closed_review_has_incomplete_target(
            feature_id, record, trunk=trunk
        ):
            # Target lifecycle repair is part of accepting the immutable merge,
            # and must run before stacked-review recovery can short-circuit the
            # sweep for an already accepted generation.
            try:
                effective_record = (
                    {**record, "target_branch": integration_branch("epic", epic_id)}
                    if epic_id
                    else record
                )
                mr = _record_to_mr(effective_record)
            except (GitError, ValueError, KeyError):
                continue
            before = bool(
                epic_id and feature_completed_recorded(feature_id, epic_id, root=trunk)
            )
            if _finalize_merged_review_record(
                feature_id, effective_record, mr, trunk=trunk
            ):
                if (
                    epic_id
                    and not before
                    and feature_completed_recorded(feature_id, epic_id, root=trunk)
                ):
                    finalized.append(feature_id)
            continue
        if _stacked_acceptance(
            record
        ) is None and persist_if_stacked_review_integration_gap(
            feature_id, record, root=trunk, accepted=bool(record.get("closed"))
        ):
            continue
        if record.get("closed"):
            feature = trunk_board.by_id.get(feature_id)
            epic = trunk_board.by_id.get(epic_id) if epic_id else None
            terminal_epic = (
                epic is not None
                and epic.tier == "epic"
                and epic.status == "completed"
                and epic.path.parent.name == "3_completed"
                and not is_trunk_pointer(epic)
            )
            if terminal_epic and feature is None and feature_id in epic.children:
                # Legacy squash merges may retain the completed child document
                # only in its source checkout. The closed review and terminal
                # parent's explicit child list bind that historical copy.
                if source_board is None:
                    source_board = merged_board(trunk)
                feature = source_board.by_id.get(feature_id)
            if (
                terminal_epic
                and feature is not None
                and feature.tier == "feature"
                and feature.parent == epic_id
                and feature.status == "completed"
                and feature.path.parent.name == "3_completed"
            ):
                # This acknowledges an already terminal parent's history; it
                # neither emits completion nor changes lifecycle state. Target
                # repair and stacked integration gaps retain priority above.
                continue
            if epic_id and not feature_completed_recorded(
                feature_id, epic_id, root=trunk
            ):
                if try_complete_feature(feature_id, root=trunk, review_merged=True):
                    finalized.append(feature_id)
            continue
        try:
            mr = _record_to_mr(record)
            snapshot = merge_request_snapshot(trunk, mr)
        except (GitError, ValueError, KeyError):
            continue
        if snapshot.get("state") != "merged":
            continue
        if not review_callback_is_current(
            feature_id, record, root=trunk, snapshot=snapshot
        ):
            continue
        record = _merged_review_record(feature_id, record, snapshot, trunk=trunk)
        _record_forge_acceptance(feature_id, record, snapshot, root=trunk)
        if str(record.get("target_branch") or "").startswith("feat/"):
            feature = merged_board(trunk).by_id.get(feature_id)
            parent_id = feature.parent if feature else None
            before_stack = bool(
                parent_id
                and feature_completed_recorded(feature_id, parent_id, root=trunk)
            )
            if _reconcile_stacked_acceptance(feature_id, record, snapshot, trunk=trunk):
                if (
                    parent_id
                    and not before_stack
                    and feature_completed_recorded(feature_id, parent_id, root=trunk)
                ):
                    finalized.append(feature_id)
                continue
        mr = _record_to_mr(record)
        epic_id = _review_target_epic(record)
        before = (
            feature_completed_recorded(feature_id, epic_id, root=trunk)
            if epic_id
            else True
        )
        if _finalize_merged_review_record(
            feature_id, record, mr, trunk=trunk, snapshot=snapshot
        ):
            if (
                epic_id
                and not before
                and feature_completed_recorded(feature_id, epic_id, root=trunk)
            ):
                finalized.append(feature_id)
    return finalized


def _closed_review_has_incomplete_target(
    feature_id: str, record: dict[str, object], *, trunk: Path
) -> bool:
    epic_id = _review_target_epic(record)
    entry = get_integration_worktree(trunk, "epic", epic_id) if epic_id else None
    if entry is None or not entry.path.is_dir():
        return False
    try:
        meta = read_doc_in_worktree(feature_id, entry.path).meta
    except NotFound:
        return False
    return (
        meta.tier == "feature"
        and meta.parent == epic_id
        and meta.path.parent.name in ("1_backlog", "2_active")
    )


def _review_target_epic(record: dict[str, object]) -> str | None:
    target = str(
        record.get("integration_target_branch")
        if record.get("closed") and record.get("integration_target_branch")
        else record.get("target_branch") or ""
    )
    prefix = "epic/"
    if target.startswith(prefix):
        return target.removeprefix(prefix)
    return None


def _merged_review_record(
    feature_id: str,
    record: dict[str, object],
    snapshot: dict[str, object],
    *,
    trunk: Path,
) -> dict[str, object]:
    """Use the forge's accepted base after native retargeting of a stack."""

    live_target = str(snapshot.get("target_branch") or "").strip()
    if not live_target or live_target == record.get("target_branch"):
        return record
    updated = dict(record)
    updated["target_branch"] = live_target
    feature = merged_board(trunk).by_id.get(feature_id)
    if (
        feature is not None
        and feature.tier == "feature"
        and feature.parent is not None
        and live_target == integration_branch("epic", feature.parent)
    ):
        _update_record(trunk, feature_id, {"target_branch": live_target})
    return updated


def _git_ancestor(root: Path, ancestor: object, descendant: object) -> bool:
    if not isinstance(ancestor, str) or not isinstance(descendant, str):
        return False
    if not all(re.fullmatch(r"[0-9a-f]{40}", item) for item in (ancestor, descendant)):
        return False
    try:
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", ancestor, descendant],
                cwd=root,
                capture_output=True,
                timeout=5,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _reconcile_stacked_acceptance(
    feature_id: str,
    record: dict[str, object],
    snapshot: dict[str, object],
    *,
    trunk: Path,
) -> bool:
    """Acknowledge a merged child review without confusing it with Epic delivery."""
    target = str(record.get("target_branch") or "")
    if not target.startswith("feat/"):
        return False
    merge_sha = snapshot.get("merge_sha")
    source = snapshot.get("source_revision")
    if snapshot.get("state") != "merged":
        return False
    if not isinstance(merge_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
        return False
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
        return False
    if snapshot.get("target_branch", target) != target:
        return False
    feature = merged_board(trunk).by_id.get(feature_id)
    predecessor_id = target.removeprefix("feat/")
    if (
        not feature
        or feature.tier != "feature"
        or not feature.parent
        or predecessor_id not in feature.depends_on
    ):
        return False
    predecessor = review_record_for_feature(predecessor_id, root=trunk)
    if not predecessor:
        return False
    receipt = {
        "url": record.get("url"),
        "target_branch": target,
        "generation": int(record.get("current_generation") or 0),
        "merge_sha": merge_sha,
        "source_revision": source,
    }
    if _stacked_acceptance(record) != receipt:
        # Capture the accepted object while the predecessor branch is still
        # reachable; fetch only refs/objects, never mutate its working tree.
        if not _git_ancestor(trunk, merge_sha, merge_sha) and not predecessor.get(
            "closed"
        ):
            try:
                subprocess.run(
                    ["git", "fetch", "--no-tags", "origin", target],
                    cwd=trunk,
                    capture_output=True,
                    timeout=20,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        _update_record(trunk, feature_id, {"stacked_acceptance": receipt})
    if not predecessor.get("closed"):
        return True

    epic_branch = integration_branch("epic", feature.parent)
    epic = get_integration_worktree(trunk, "epic", feature.parent)
    if epic is None or not epic.path.is_dir():
        return False
    epic_head = head_sha(epic.path)
    anchor = merge_sha
    if not _git_ancestor(trunk, merge_sha, epic_head):
        # Squash of the parent may omit the child's commit from Epic ancestry.
        # Its exact accepted source must contain the child merge, and the
        # parent's accepted integration commit must be on the Epic line.
        anchor = predecessor.get("stack_integration_sha") or predecessor.get(
            "accepted_merge_sha"
        )
        if not _git_ancestor(
            trunk, merge_sha, predecessor.get("accepted_source_head")
        ) or not _git_ancestor(trunk, anchor, epic_head):
            return False
    # Keep the original review URL/base immutable; only the local completion
    # operation targets the Epic. No second PR or unreviewed merge is created.
    if not _accept_current_review_generation(
        feature_id,
        record,
        snapshot,
        root=trunk,
        integration_target=epic_branch,
        integration_sha=anchor,
    ):
        return False
    integrated = {**record, "target_branch": epic_branch}
    if not _finalize_merged_review_record(
        feature_id,
        integrated,
        _record_to_mr(integrated),
        trunk=trunk,
    ):
        return True
    return True


def _finalize_merged_review_record(
    feature_id: str,
    record: dict[str, object],
    mr: MergeRequest,
    *,
    trunk: Path,
    snapshot: dict[str, object] | None = None,
) -> bool:
    from cascade.boss.rollup import try_complete_feature

    try:
        _sync_merged_target(trunk, mr)
        epic_root = _close_merged_feature_on_target(feature_id, record, trunk=trunk)
        # The accepted source tree may still have an active feature document.
        # Publish its terminal lifecycle commit before acknowledging closure.
        push_branch(epic_root, mr.target_branch)
        if snapshot is not None and not _accept_current_review_generation(
            feature_id, record, snapshot, root=trunk
        ):
            return False
        complete = try_complete_feature(
            feature_id,
            root=trunk,
            review_merged=True,
            review_generation=int(record.get("current_generation") or 0),
        )
        if not complete:
            from cascade.lifecycle_review_gate import require_lifecycle_review_gate
            from cascade.workspace.architecture_review import ArchitectureProposalError

            blocker = {
                "code": "closeout_pending",
                "message": "Merged; lifecycle closeout is pending",
            }
            try:
                require_lifecycle_review_gate(feature_id, "closeout", root=trunk)
            except ArchitectureProposalError as exc:
                blocker = {"code": exc.code, "message": str(exc)}
            _update_record(trunk, feature_id, {"closeout_blocker": blocker})
        else:
            _update_record(trunk, feature_id, {"closeout_blocker": None})
        return complete
    except (BoardError, OSError) as exc:
        _LOG.warning("could not finalize merged review for %s: %s", feature_id, exc)
        return False


def _close_merged_feature_on_target(
    feature_id: str, record: dict[str, object], *, trunk: Path
) -> Path:
    """Persist completion on the epic line after its accepted review merge.

    The source feature doc is moved locally after initial MR publication. That
    local lifecycle commit is not part of the forge merge, so the accepted epic
    tree can still contain the active copy. Complete that copy before recording
    the review as closed or releasing dependent Features.
    """

    epic_id = _review_target_epic(record)
    entry = get_integration_worktree(trunk, "epic", epic_id) if epic_id else None
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing for merged feature {feature_id}")
    doc = read_doc_in_worktree(feature_id, entry.path)
    if doc.meta.tier != "feature" or doc.meta.parent != epic_id:
        raise GitError(f"merged feature target mismatch: {feature_id}")
    if doc.meta.status == "completed" and doc.meta.path.parent.name == "3_completed":
        return entry.path
    if (doc.meta.status, doc.meta.path.parent.name) not in (
        ("backlog", "1_backlog"),
        ("active", "2_active"),
    ):
        raise GitError(f"merged feature is not open on epic branch: {feature_id}")
    previous_path = doc.meta.path
    doc.meta.status = "completed"
    doc.meta.path = (
        entry.path / "docs/features/3_completed" / previous_path.name
    ).resolve()
    save_doc(doc, previous_path=previous_path, root=entry.path)
    return entry.path


def poll_feature_reviews(root: Path) -> None:
    trunk = locate_trunk(root)
    state = _load(trunk)
    from cascade.stacked_review_recovery import (
        persist_if_stacked_review_integration_gap,
    )

    for feature_id, record in list(state.items()):
        if record.get("closed") or record.get("kind") == "epic_close":
            continue
        try:
            mr = _record_to_mr(record)
            snapshot = merge_request_snapshot(trunk, mr)
        except (GitError, ValueError):
            continue
        seen = {str(item) for item in record.get("seen_comments", [])}
        for row in snapshot.get("comments", []):
            if not isinstance(row, dict):
                continue
            comment_id = str(
                row.get("id") or row.get("databaseId") or row.get("created_at") or ""
            )
            body = str(row.get("body") or row.get("note") or "").strip()
            author_raw = row.get("author") or row.get("user") or {}
            author = (
                str(author_raw.get("login") or author_raw.get("username") or "reviewer")
                if isinstance(author_raw, dict)
                else str(author_raw)
            )
            if not comment_id or comment_id in seen or not body:
                continue
            seen.add(comment_id)
            if "<!-- cascade-agent-reply -->" in body:
                continue
            append_event(
                feature_id,
                Event(
                    type="MergeRequestComment",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "feature_id": feature_id,
                        "comment_id": comment_id,
                        "author": author,
                        "body": body,
                        "merge_request_url": mr.url,
                        "instruction": "Assess holistically, mint fixer tasks when code changes are needed, and reply through reply_merge_request_comment.",
                    },
                    dest=feature_id,
                ),
                root=trunk,
            )
        # Persist deliveries before any later publication/finalization failure.
        # Merge with the latest record so parallel reviews cannot be reopened.
        _update_record(trunk, feature_id, {"seen_comments": sorted(seen)})
        if snapshot.get("state") == "merged":
            if not review_callback_is_current(
                feature_id, record, root=trunk, snapshot=snapshot
            ):
                continue
            record = _merged_review_record(feature_id, record, snapshot, trunk=trunk)
            _record_forge_acceptance(feature_id, record, snapshot, root=trunk)
            if _reconcile_stacked_acceptance(feature_id, record, snapshot, trunk=trunk):
                continue
            mr = _record_to_mr(record)
            if persist_if_stacked_review_integration_gap(
                feature_id, record, root=trunk, accepted=True
            ):
                continue
            if not _finalize_merged_review_record(
                feature_id, record, mr, trunk=trunk, snapshot=snapshot
            ):
                # Do not acknowledge completion until the local epic worktree
                # contains the exact tree accepted by the forge.
                continue
        else:
            current = review_record_for_feature(feature_id, root=trunk)
            if current is None or current.get("closed"):
                continue
            entry = get_integration_worktree(trunk, "feature", feature_id)
            if entry is not None:
                try:
                    from cascade.feature.publication import prepare_feature_publication

                    publication = prepare_feature_publication(feature_id, root=trunk)
                    remote_lease_sha = getattr(publication, "remote_lease_sha", None)
                    if remote_lease_sha is not None:
                        push_branch(
                            entry.path,
                            mr.source_branch,
                            force_with_lease=remote_lease_sha,
                        )
                    else:
                        push_branch(entry.path, mr.source_branch)
                except GitError:
                    # Fail closed: never publish checkpoint/merge noise after the
                    # initial review was opened.
                    continue


def _sync_merged_target(trunk: Path, mr: MergeRequest) -> str:
    prefix = "epic/"
    if not mr.target_branch.startswith(prefix):
        raise GitError(f"unexpected feature review target: {mr.target_branch}")
    epic_id = mr.target_branch.removeprefix(prefix)
    entry = get_integration_worktree(trunk, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise GitError(f"epic worktree missing: {epic_id}")
    return fast_forward_branch(entry.path, mr.target_branch)


def reply_feature_review(feature_id: str, body: str, *, root: Path) -> str:
    state = _load(locate_trunk(root))
    record = state.get(feature_id)
    if record is None:
        raise NotFound(f"no merge request for {feature_id}")
    mr = _record_to_mr(record)
    reply_to_merge_request(
        locate_trunk(root),
        mr.url,
        body.rstrip() + "\n\n<!-- cascade-agent-reply -->",
    )
    return mr.url


def _record_to_mr(record: dict[str, object]) -> MergeRequest:
    return MergeRequest(
        url=str(record["url"]),
        number=str(record["number"]) if record.get("number") is not None else None,
        forge=str(record["forge"]),  # type: ignore[arg-type]
        source_branch=str(record["source_branch"]),
        target_branch=str(record["target_branch"]),
        draft=bool(record.get("draft", True)),
    )


def live_merge_request_target_branch(
    record: dict[str, object], *, root: Path
) -> str | None:
    """Read the forge-reported PR/MR base branch without mutating durable state."""

    url = str(record.get("url") or "").strip()
    if not url:
        return None
    trunk = locate_trunk(root)
    try:
        mr = _record_to_mr(record)
        snapshot = merge_request_snapshot(trunk, mr)
    except (GitError, ValueError, KeyError):
        return None
    live = str(snapshot.get("target_branch") or "").strip()
    return live or None


def persist_review_target_branch(
    feature_id: str, target_branch: str, *, root: Path
) -> None:
    """Mirror a verified forge base into the durable review registry."""

    trunk = locate_trunk(root)
    _update_record(trunk, feature_id, {"target_branch": target_branch})


def persist_stacked_reconciliation_review(
    feature_id: str,
    mr: MergeRequest,
    *,
    action_id: str,
    originating_review: dict[str, object],
    root: Path,
) -> dict[str, object]:
    """Replace a stranded stacked-review record with its Epic-targeted review.

    A review registry has one current review per Feature.  Keep the accepted
    predecessor-targeted review as explicit provenance while making the new
    Epic-targeted review the one that the normal poller can reconcile.
    """

    trunk = locate_trunk(root)
    provenance = dict(originating_review)
    reconciliation = {
        "action_id": action_id,
        "originating_review": provenance,
    }
    current = review_record_for_feature(feature_id, root=trunk)
    if current is not None:
        prior = current.get("stacked_reconciliation")
        if isinstance(prior, dict) and prior.get("action_id") not in (None, action_id):
            raise GitError(
                f"{feature_id} already has a different stacked reconciliation"
            )
        if (
            current.get("url") == mr.url
            and current.get("target_branch") == mr.target_branch
        ):
            return current
    record = _update_record(
        trunk,
        feature_id,
        {
            "url": mr.url,
            "number": mr.number,
            "forge": mr.forge,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "draft": mr.draft,
            "closed": False,
            "seen_comments": [],
            "toast_notified": False,
            "stacked_reconciliation": reconciliation,
            "forge_acceptance": None,
            "stacked_acceptance": None,
            "integration_target_branch": None,
            "stack_integration_sha": None,
        },
        create=True,
    )
    assert record is not None
    return record
