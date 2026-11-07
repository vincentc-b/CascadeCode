"""Durable, human-granted authority for dependency setup operations.

Approvals are append-only records owned by the epic's tracking repository.  The
guard in this module deliberately knows nothing about provider permissions or
execution policy: callers must pass it immediately before a setup mutation.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from cascade.board.gitutil import commit_paths, has_git
from cascade.board.lock import process_lock
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    InstallationApproval,
    InstallationBinding,
    InvalidDependencyManifest,
    manifest_path,
    require_dependency_manifest,
)
from cascade.workspace.integration_worktree import locate_trunk

_APPROVAL_SIDECAR_DIR = "_dependency_installation_approvals"
_SCHEMA_VERSION = 2
_LEGACY_SCHEMA_VERSION = 1
_UNKNOWN_EXACT_VALUES = frozenset(
    {
        "unknown",
        "unspecified",
        "unresolved",
        "not known",
        "n/a",
        "not applicable",
        "latest",
    }
)
_T = TypeVar("_T")


class DependencyApprovalError(ValueError):
    """Base error for dependency installation approval operations."""


class InstallationApprovalDenied(DependencyApprovalError):
    """The requested setup mutation has no current matching human approval."""


@dataclass(frozen=True, slots=True)
class AuthenticatedHuman:
    """Identity supplied by an authenticated human-facing API boundary."""

    subject: str

    def __post_init__(self) -> None:
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise DependencyApprovalError("authenticated human subject is required")


def approval_path(epic_id: str, *, root: Path) -> Path:
    """Return the approval journal beside the epic's manifest sidecar."""

    manifests = manifest_path(epic_id, root=root).parent
    return manifests.parent / _APPROVAL_SIDECAR_DIR / f"{epic_id}.json"


def read_installation_approvals(
    epic_id: str, *, root: Path
) -> tuple[InstallationApproval, ...]:
    """Reload all immutable approval records, or an empty journal if absent."""

    path = approval_path(epic_id, root=root)
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyApprovalError(
            f"cannot read dependency installation approvals for {epic_id}"
        ) from exc
    if not isinstance(raw, dict):
        raise DependencyApprovalError("installation approval journal must be an object")
    if set(raw) != {"version", "epic_id", "approvals"}:
        raise DependencyApprovalError(
            "installation approval journal has invalid fields"
        )
    schema_version = raw.get("version")
    if schema_version not in {_LEGACY_SCHEMA_VERSION, _SCHEMA_VERSION}:
        raise DependencyApprovalError(
            "unsupported installation approval schema version"
        )
    if raw.get("epic_id") != epic_id:
        raise DependencyApprovalError(
            "installation approval epic_id does not match path"
        )
    rows = raw.get("approvals")
    if not isinstance(rows, list) or not rows:
        raise DependencyApprovalError("persisted approval journal must not be empty")
    try:
        approvals = tuple(
            InstallationApproval.from_dict(row, schema_version=schema_version)
            for row in rows
        )
    except InvalidDependencyManifest as exc:
        raise DependencyApprovalError(
            "invalid persisted installation approval"
        ) from exc
    ids = [row.approval_id for row in approvals]
    if len(ids) != len(set(ids)):
        raise DependencyApprovalError("installation approval IDs must be unique")
    return approvals


def approve_dependency_installations(
    epic_id: str,
    dependency_ids: Sequence[str],
    *,
    approver: AuthenticatedHuman,
    root: Path,
    approved_at: datetime | None = None,
) -> tuple[InstallationApproval, ...]:
    """Atomically append one independent approval for each current entry.

    A batch is only a user interaction convenience.  Every returned item has a
    distinct ID and complete reviewed-entry snapshot.  No partial batch is
    written when any requested entry is missing or lacks exact authority data.
    """

    if not isinstance(approver, AuthenticatedHuman):
        raise DependencyApprovalError("an authenticated human approver is required")
    if isinstance(dependency_ids, (str, bytes)):
        raise DependencyApprovalError("dependency IDs must be supplied as a sequence")
    ids = tuple(dependency_ids)
    if not ids:
        raise DependencyApprovalError("at least one dependency must be approved")
    if not all(isinstance(row, str) and row.strip() for row in ids):
        raise DependencyApprovalError("dependency IDs must be non-blank strings")
    if len(ids) != len(set(ids)):
        raise DependencyApprovalError("a dependency may appear only once per batch")
    when = approved_at or datetime.now(timezone.utc)
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise DependencyApprovalError("approved_at must be timezone-aware")

    with process_lock:
        manifest = require_dependency_manifest(epic_id, root=root)
        if not manifest.is_current_schema:
            raise DependencyApprovalError(
                "legacy dependency manifests cannot grant installation authority"
            )
        entries = {row.dependency_id: row for row in manifest.dependencies}
        missing = [
            dependency_id for dependency_id in ids if dependency_id not in entries
        ]
        if missing:
            raise DependencyApprovalError(
                f"current manifest has no dependency: {', '.join(missing)}"
            )
        requested = tuple(entries[dependency_id] for dependency_id in ids)
        for entry in requested:
            _require_exact_authority(entry)
        existing = read_installation_approvals(epic_id, root=root)
        created = tuple(
            InstallationApproval(
                approval_id=f"dep-approval-{uuid.uuid4()}",
                binding=InstallationBinding.from_entry(entry),
                approver_id=approver.subject,
                approved_at=when,
                reviewed_manifest_revision=manifest.revision,
                reviewed_entry=entry,
            )
            for entry in requested
        )
        path = approval_path(epic_id, root=root)
        _write_approval_journal(path, epic_id, (*existing, *created))
        if has_git(path.parent):
            from cascade.workspace.integration_worktree import (
                git_root_for_path,
                invalidate_merged_board,
            )

            commit_root = git_root_for_path(path)
            commit_paths(
                commit_root,
                [path],
                f"docs: {epic_id} approve dependency installation",
            )
            invalidate_merged_board(locate_trunk(commit_root))
    return created


def current_installation_approval(
    epic_id: str,
    dependency_id: str,
    approval_id: str,
    *,
    root: Path,
) -> InstallationApproval | None:
    """Return the named approval only when its current entry binding still matches."""

    manifest = require_dependency_manifest(epic_id, root=root)
    if not manifest.is_current_schema:
        return None
    entry = next(
        (row for row in manifest.dependencies if row.dependency_id == dependency_id),
        None,
    )
    if entry is None:
        return None
    approval = next(
        (
            row
            for row in read_installation_approvals(epic_id, root=root)
            if row.approval_id == approval_id
        ),
        None,
    )
    if (
        approval is None
        or approval.schema_version != _SCHEMA_VERSION
        or approval.binding != InstallationBinding.from_entry(entry)
    ):
        return None
    return approval


def require_installation_approval(
    epic_id: str,
    dependency_id: str,
    approval_id: str | None,
    attempted_operation: str,
    *,
    root: Path,
) -> InstallationApproval:
    """Fail closed unless one current approval authorizes this exact operation."""

    if not isinstance(approval_id, str) or not approval_id.strip():
        raise InstallationApprovalDenied("dependency setup requires an approval ID")
    approval = current_installation_approval(
        epic_id, dependency_id, approval_id, root=root
    )
    if approval is None:
        raise InstallationApprovalDenied(
            "dependency setup approval is missing, stale, or bound to another entry"
        )
    if attempted_operation != approval.binding.operation:
        raise InstallationApprovalDenied(
            "attempted dependency operation does not match its approval"
        )
    return approval


def invoke_approved_installation(
    epic_id: str,
    dependency_id: str,
    approval_id: str | None,
    attempted_operation: str,
    mutation: Callable[[], _T],
    *,
    root: Path,
) -> _T:
    """Guard the operation boundary, then invoke a caller-owned setup mutation.

    This is not an installer.  It is the narrow boundary slice-B runners call
    immediately before their mutation; provider sandbox settings cannot bypass
    it.  Read-only discovery continues to use its existing APIs directly.
    """

    require_installation_approval(
        epic_id,
        dependency_id,
        approval_id,
        attempted_operation,
        root=root,
    )
    return mutation()


def _require_exact_authority(entry: DependencyEntry) -> None:
    if not entry.target_environment.is_fully_specified:
        raise DependencyApprovalError(
            f"dependency {entry.dependency_id} has unknown target environment"
        )
    exact = {
        "version": entry.version,
        "source": entry.source,
        "digest": entry.digest,
    }
    for field, value in exact.items():
        normalized = " ".join(value.strip().casefold().replace("-", " ").split())
        if normalized in _UNKNOWN_EXACT_VALUES or re.search(
            r"(^|[/:._?&=])latest($|[/:._?&=])", value.casefold()
        ):
            raise DependencyApprovalError(
                f"dependency {entry.dependency_id} has unknown exact {field}"
            )


def _write_approval_journal(
    path: Path,
    epic_id: str,
    approvals: Sequence[InstallationApproval],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "epic_id": epic_id,
        "approvals": [row.to_dict() for row in approvals],
    }
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
