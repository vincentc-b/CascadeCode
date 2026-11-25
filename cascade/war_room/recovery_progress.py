"""Bounded read-only consumer for published recovery progress pages."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cascade.board.context import (
    get_project_context,
    resolve_root,
    resolve_tracking_root,
)
from cascade.watchdog.audit_lane import canonical_audit_root

SCHEMA_VERSION = 1
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MAX_SOURCE_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_FILE_BYTES = 512 * 1024
_PUBLIC_ENTRY_FIELDS = (
    "schema_version",
    "entry_id",
    "entry_revision",
    "action_id",
    "original_incident_id",
    "generation",
    "graph_id",
    "affected_work_id",
    "owner",
    "attempt_number",
    "claim_id",
    "state",
    "stage",
    "occurred_at",
    "observed_at",
    "valid_until",
    "freshness",
    "provenance",
    "safe_reason",
    "prerequisite",
    "next_step",
    "target",
    "verification_ref",
    "receipt_refs",
    "milestone_refs",
)
_STATES = frozenset(
    {
        "requested_queued",
        "acknowledged",
        "investigating",
        "executing",
        "waiting_blocked",
        "retryable_failed",
        "exhausted",
        "verification_pending",
        "verified_complete",
        "stale_unavailable",
    }
)
_SAFE_PUBLIC_TEXT = re.compile(r"^[A-Za-z0-9 _./:@+\-=#?]*$", re.ASCII)


class RecoveryProgressRequestError(ValueError):
    """The request or opaque cursor is invalid."""


class RecoveryProgressRevisionChanged(Exception):
    """The cursor names an immutable revision that is no longer current."""

    def __init__(self, work_id: str, previous: str, current: str) -> None:
        self.work_id = work_id
        self.previous = previous
        self.current = current

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "work_id": self.work_id,
            "revision": self.current,
            "error": {
                "code": "revision_changed",
                "message": "published recovery progress changed; restart without a cursor",
                "restart": True,
                "previous_revision": self.previous,
                "current_revision": self.current,
            },
        }


@dataclass(slots=True)
class _Budget:
    remaining: int = MAX_SOURCE_BYTES


def _base(root: Path) -> Path:
    return (
        canonical_audit_root(resolve_root(root))
        / ".cascade"
        / "recovery_progress"
        / "v1"
    )


def _identities(root: Path) -> tuple[str, str]:
    product = canonical_audit_root(resolve_root(root))
    project = get_project_context()
    if project is not None and product == project.target.root.resolve():
        return str(project.target.repository_key), str(project.tracking.repository_key)
    tracking = resolve_tracking_root(product)
    return (
        "repository-" + hashlib.sha256(product.as_uri().encode()).hexdigest()[:24],
        "repository-" + hashlib.sha256(tracking.as_uri().encode()).hexdigest()[:24],
    )


def _work_root(root: Path, work_id: str) -> Path:
    digest = hashlib.sha256(work_id.encode()).hexdigest()
    return _base(root) / "work" / digest


def _read_json(path: Path, budget: _Budget, *, root: Path) -> Mapping[str, Any]:
    anchor = canonical_audit_root(resolve_root(root))
    try:
        relative = path.relative_to(anchor)
    except ValueError as exc:
        raise OSError("published evidence path escapes the product root") from exc
    common = getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | common | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(anchor, directory_flags)
    try:
        for part in relative.parts[:-1]:
            child_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        fd = os.open(relative.parts[-1], os.O_RDONLY | common, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("published evidence is not a regular file")
        if info.st_size > MAX_FILE_BYTES or info.st_size > budget.remaining:
            raise OSError("published evidence exceeds the source-byte budget")
        chunks: list[bytes] = []
        remaining = info.st_size + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != info.st_size:
            raise OSError("published evidence changed while reading")
        budget.remaining -= len(raw)
        loaded = json.loads(raw)
        if not isinstance(loaded, Mapping):
            raise OSError("published evidence is not a JSON object")
        return loaded
    finally:
        os.close(fd)


def _relative_path(value: object, *, prefix: str) -> Path:
    if not isinstance(value, str):
        raise OSError("published evidence path is missing")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.startswith(prefix):
        raise OSError("published evidence path is unsafe")
    return path


def _cursor(work_id: str, revision: str, offset: int) -> str:
    raw = json.dumps(
        {"v": 1, "work_id": work_id, "revision": revision, "offset": offset},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode_cursor(value: str) -> Mapping[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryProgressRequestError("invalid recovery progress cursor") from exc
    if (
        not isinstance(decoded, Mapping)
        or decoded.get("v") != 1
        or not isinstance(decoded.get("work_id"), str)
        or not isinstance(decoded.get("revision"), str)
        or not isinstance(decoded.get("offset"), int)
        or isinstance(decoded.get("offset"), bool)
        or int(decoded["offset"]) < 0
    ):
        raise RecoveryProgressRequestError("invalid recovery progress cursor")
    return decoded


def _pending(work_id: str, code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "work_id": work_id,
        "revision": None,
        "observed_at": None,
        "expires_at": None,
        "completeness": "pending",
        "lag": {"backlog_count": None, "oldest_pending_at": None},
        "primary": None,
        "items": [],
        "next_cursor": None,
        "error": {"code": code, "message": message, "retryable": True},
    }


def _validate_header(
    pointer: Mapping[str, Any], manifest: Mapping[str, Any], work_id: str, root: Path
) -> str | None:
    if (
        pointer.get("schema_version") != SCHEMA_VERSION
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        return "incompatible"
    if pointer.get("work_id") != work_id or manifest.get("work_id") != work_id:
        return "wrong_work_id"
    revision = pointer.get("revision")
    if not isinstance(revision, str) or manifest.get("revision") != revision:
        return "revision_mismatch"
    identity = manifest.get("repository_identity")
    product, tracking = _identities(root)
    if (
        not isinstance(identity, Mapping)
        or identity.get("product") != product
        or identity.get("tracking") != tracking
    ):
        return "wrong_root"
    pages = manifest.get("pages")
    if (
        not isinstance(pages, list)
        or not pages
        or len(pages) > 100_000
        or manifest.get("page_count") != len(pages)
        or not isinstance(manifest.get("entry_count"), int)
    ):
        return "incompatible"
    return None


def _public_entry(row: object, work_id: str) -> dict[str, object] | None:
    if not isinstance(row, Mapping):
        return None
    if (
        row.get("schema_version") != SCHEMA_VERSION
        or row.get("affected_work_id") != work_id
        or not isinstance(row.get("entry_id"), str)
        or not isinstance(row.get("action_id"), str)
        or not isinstance(row.get("generation"), str)
        or row.get("state") not in _STATES
        or not isinstance(row.get("receipt_refs"), list)
        or not isinstance(row.get("milestone_refs"), list)
    ):
        return None
    bounded_text = (
        "owner",
        "stage",
        "safe_reason",
        "prerequisite",
        "next_step",
        "target",
        "verification_ref",
    )
    for field in bounded_text:
        value = row.get(field)
        if value is not None and (
            not isinstance(value, str)
            or len(value) > 240
            or _SAFE_PUBLIC_TEXT.fullmatch(value) is None
        ):
            return None
    for field in ("receipt_refs", "milestone_refs"):
        refs = row[field]
        if len(refs) > 100 or any(
            not isinstance(ref, str)
            or len(ref) > 512
            or any(ord(char) < 32 for char in ref)
            for ref in refs
        ):
            return None
    if row.get("freshness") not in {"fresh", "unavailable"} or row.get(
        "provenance"
    ) not in {"modern", "legacy_unknown"}:
        return None
    # Immutable pages are producer-owned, but a corrupt or replaced page must
    # never turn unknown metadata into a public field.
    return {field: row.get(field) for field in _PUBLIC_ENTRY_FIELDS}


def read_recovery_progress(
    root: Path,
    work_id: str,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
    budget: _Budget | None = None,
) -> dict[str, object]:
    """Read one revision-bound page without opening producer or source state."""

    if not work_id or len(work_id) > 240 or any(ord(char) < 32 for char in work_id):
        raise RecoveryProgressRequestError("work_id is required")
    if isinstance(limit, bool) or limit < 1 or limit > MAX_LIMIT:
        raise RecoveryProgressRequestError("limit must be between 1 and 100")
    decoded = _decode_cursor(cursor) if cursor is not None else None
    if decoded is not None and decoded["work_id"] != work_id:
        raise RecoveryProgressRequestError("cursor does not match work_id")
    read_budget = budget or _Budget()
    work_root = _work_root(root, work_id)
    try:
        pointer = _read_json(work_root / "current.json", read_budget, root=root)
        manifest_rel = _relative_path(pointer.get("manifest"), prefix="revisions/")
        manifest = _read_json(work_root / manifest_rel, read_budget, root=root)
    except FileNotFoundError:
        return _pending(
            work_id, "evidence_missing", "recovery progress has not been published"
        )
    except (OSError, json.JSONDecodeError):
        return _pending(
            work_id,
            "evidence_unavailable",
            "published recovery progress is unavailable",
        )
    problem = _validate_header(pointer, manifest, work_id, root)
    if problem is not None:
        return _pending(
            work_id,
            problem,
            "published recovery progress cannot be trusted for this workspace",
        )
    revision = str(pointer["revision"])
    if manifest.get("completeness") not in {
        "complete",
        "incomplete",
        "pending",
    } or not isinstance(manifest.get("lag"), Mapping):
        return _pending(
            work_id,
            "evidence_incompatible",
            "published recovery progress has invalid completeness",
        )
    if decoded is not None and decoded["revision"] != revision:
        raise RecoveryProgressRevisionChanged(
            work_id, str(decoded["revision"]), revision
        )
    current = now or datetime.now(timezone.utc)
    try:
        expires = datetime.fromisoformat(str(manifest["expires_at"]))
        if expires.tzinfo is None or expires.astimezone(
            timezone.utc
        ) <= current.astimezone(timezone.utc):
            return _pending(
                work_id, "evidence_stale", "published recovery progress has expired"
            )
    except (KeyError, ValueError):
        return _pending(
            work_id,
            "evidence_incompatible",
            "published recovery progress has invalid freshness",
        )

    offset = int(decoded["offset"]) if decoded is not None else 0
    entry_count = int(manifest["entry_count"])
    if offset > entry_count:
        raise RecoveryProgressRequestError("cursor offset is outside the projection")
    pages = manifest["pages"]
    assert isinstance(pages, list)
    items: list[dict[str, object]] = []
    selected_primary: dict[str, object] | None = None
    index = offset
    while index < entry_count and len(items) < limit:
        page_number = index // 50
        try:
            page_rel = _relative_path(pages[page_number], prefix="pages/")
            revision_root = work_root / "revisions" / revision
            page = _read_json(revision_root / page_rel, read_budget, root=root)
        except (IndexError, FileNotFoundError, OSError, json.JSONDecodeError):
            return _pending(
                work_id,
                "page_unavailable",
                "an immutable recovery progress page is unavailable",
            )
        rows = page.get("items")
        if (
            page.get("schema_version") != SCHEMA_VERSION
            or page.get("work_id") != work_id
            or page.get("revision") != revision
            or not isinstance(rows, list)
            or len(rows) > 50
        ):
            return _pending(
                work_id,
                "page_incompatible",
                "an immutable recovery progress page is incompatible",
            )
        within = index % 50
        while within < len(rows) and len(items) < limit:
            row = _public_entry(rows[within], work_id)
            if row is None:
                return _pending(
                    work_id,
                    "page_incompatible",
                    "an immutable recovery progress entry is incompatible",
                )
            items.append(row)
            if index == 0:
                selected_primary = row
            within += 1
            index += 1
        if len(rows) < 50 and within >= len(rows) and index < entry_count:
            return _pending(
                work_id,
                "page_incomplete",
                "an immutable recovery progress page is incomplete",
            )
    if selected_primary is None and entry_count:
        try:
            first_rel = _relative_path(pages[0], prefix="pages/")
            first_page = _read_json(
                work_root / "revisions" / revision / first_rel,
                read_budget,
                root=root,
            )
            first_rows = first_page.get("items")
            candidate = (
                _public_entry(first_rows[0], work_id)
                if isinstance(first_rows, list) and first_rows
                else None
            )
            if candidate is not None:
                selected_primary = candidate
            else:
                return _pending(
                    work_id,
                    "page_incompatible",
                    "the primary recovery progress entry is incompatible",
                )
        except (IndexError, FileNotFoundError, OSError, json.JSONDecodeError):
            return _pending(
                work_id,
                "page_unavailable",
                "the primary recovery progress entry is unavailable",
            )
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "work_id": work_id,
        "revision": revision,
        "observed_at": manifest.get("observed_at"),
        "expires_at": manifest.get("expires_at"),
        "completeness": manifest.get("completeness"),
        "lag": manifest.get("lag"),
        "primary": selected_primary,
        "items": items,
        "entry_count": entry_count,
        "next_cursor": _cursor(work_id, revision, index)
        if index < entry_count
        else None,
    }
    if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_RESPONSE_BYTES:
        return _pending(
            work_id,
            "response_budget",
            "recovery progress exceeds the response-byte budget",
        )
    return result


def read_recovery_progress_many(
    root: Path, work_ids: list[str]
) -> dict[str, dict[str, object]]:
    """Read board primaries under one aggregate source/row budget."""

    budget = _Budget()
    results: dict[str, dict[str, object]] = {}
    remaining_rows = MAX_LIMIT
    for work_id in dict.fromkeys(work_ids):
        if remaining_rows <= 0:
            results[work_id] = _pending(
                work_id, "row_budget", "board recovery progress row budget is exhausted"
            )
            continue
        result = read_recovery_progress(root, work_id, limit=1, budget=budget)
        results[work_id] = result
        remaining_rows -= len(result["items"])
    return results


def board_recovery_projection(
    progress: Mapping[str, object],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    """Return the compatible primary summary and additive version metadata."""

    primary = progress.get("primary")
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "revision": progress.get("revision"),
        "entry_id": primary.get("entry_id") if isinstance(primary, Mapping) else None,
        "action_id": primary.get("action_id") if isinstance(primary, Mapping) else None,
        "freshness": primary.get("freshness") if isinstance(primary, Mapping) else None,
        "count": progress.get("entry_count", 0),
        "next_cursor": progress.get("next_cursor"),
        "completeness": progress.get("completeness"),
        "error": progress.get("error"),
    }
    if not isinstance(primary, Mapping):
        return None, metadata
    state = str(primary.get("state") or "stale_unavailable")
    coarse = "blocked" if state in {"waiting_blocked", "exhausted"} else "investigating"
    if state in {"retryable_failed", "stale_unavailable"}:
        coarse = "failed"
    incident = {
        "state": coarse,
        "reason": primary.get("safe_reason")
        or primary.get("stage")
        or "Recovery evidence is available.",
        "owner": {"kind": "recovery_owner", "work_id": primary.get("owner")},
        "affected": {"branch": primary.get("target"), "paths": []},
        "last_attempt": {
            "number": primary.get("attempt_number") or 0,
            "at": primary.get("occurred_at"),
        },
        "target": {
            "kind": "action",
            "id": primary.get("action_id"),
            "href": f"/api/doc/{progress.get('work_id')}",
        },
        "next_step": primary.get("next_step"),
        "recovery_progress": metadata,
    }
    return incident, metadata


__all__ = [
    "RecoveryProgressRequestError",
    "RecoveryProgressRevisionChanged",
    "board_recovery_projection",
    "read_recovery_progress",
    "read_recovery_progress_many",
]
