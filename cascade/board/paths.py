"""Column folders, status pairing, and work-id formatting."""

from __future__ import annotations

import re
from pathlib import Path

from cascade.board.errors import SchemaError
from cascade.board.types import Column, WorkStatus, WorkTier

_TIER_DIR: dict[WorkTier, str] = {
    "epic": "epics",
    "feature": "features",
    "task": "tasks",
}
_COLUMN_DIR: dict[Column, str] = {
    "backlog": "1_backlog",
    "active": "2_active",
    "completed": "3_completed",
}
_FOLDER_COLUMN: dict[str, Column] = {folder: column for column, folder in _COLUMN_DIR.items()}
_STATUS_FOR_COLUMN: dict[Column, WorkStatus] = {
    "backlog": "backlog",
    "active": "active",
    "completed": "completed",
}
_PREFIX: dict[WorkTier, str] = {
    "epic": "epic",
    "feature": "feat",
    "task": "task",
}
_TIER_FROM_PREFIX = {prefix: tier for tier, prefix in _PREFIX.items()}
_ID_RE = re.compile(r"^(epic|feat|task)_(\d+)$")
_FILENAME_ID_RE = re.compile(
    r"^(?:epic_\d{3}|feat_\d{3}(?:_\d{3})?|task_\d{3}(?:_\d{3}_\d{3})?)"
)


def column_dir(tier: WorkTier, column: Column) -> Path:
    """Relative directory `docs/{epics|features|tasks}/{1_backlog|2_active|3_completed}`."""

    try:
        tier_dir = _TIER_DIR[tier]
        column_folder = _COLUMN_DIR[column]
    except KeyError as exc:
        raise SchemaError(f"unknown tier or column: {tier!r} {column!r}") from exc
    return Path("docs") / tier_dir / column_folder


def status_for_column(column: Column) -> WorkStatus:
    """Default status written by move_doc for a destination column."""

    try:
        return _STATUS_FOR_COLUMN[column]
    except KeyError as exc:
        raise SchemaError(f"unknown column: {column!r}") from exc


def column_for_status(status: WorkStatus) -> Column:
    """Column that legally holds `status`."""

    if status in ("backlog", "ready_to_plan"):
        return "backlog"
    if status in ("active", "blocked", "cancelling"):
        return "active"
    if status in ("completed", "cancelled"):
        return "completed"
    raise SchemaError(f"unknown status: {status!r}")


def legal_folder(status: WorkStatus) -> str:
    """Folder name (`1_backlog`, `2_active`, or `3_completed`) for `status`."""

    return _COLUMN_DIR[column_for_status(status)]


def parse_work_id(value: str) -> tuple[WorkTier, int]:
    """Parse `epic_001`, `feat_012`, or `task_003` into `(tier, number)`."""

    match = _ID_RE.fullmatch(value)
    if match is None:
        raise SchemaError(f"invalid work id: {value!r}")
    prefix, number = match.group(1), int(match.group(2))
    if number < 1:
        raise SchemaError(f"invalid work id: {value!r}")
    return _TIER_FROM_PREFIX[prefix], number


def format_work_id(tier: WorkTier, number: int) -> str:
    """Format a tier and positive integer as a zero-padded work id."""

    try:
        prefix = _PREFIX[tier]
    except KeyError as exc:
        raise SchemaError(f"unknown tier: {tier!r}") from exc
    if number < 1:
        raise SchemaError("work id number must be positive")
    return f"{prefix}_{number:03d}"


def filename_work_id(path: Path) -> str | None:
    """Return the work id encoded at the start of a filename, if any."""

    match = _FILENAME_ID_RE.match(path.stem)
    if match is None:
        return None
    return match.group(0)


def slugify(title: str) -> str:
    """Stable filename slug. The id, not the slug, is the lookup key."""

    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "untitled"


def infer_repo_root(path: Path) -> Path | None:
    """Repo root is the parent of `docs/{epics|features|tasks}/...`."""

    parts = Path(path).resolve().parts
    tier_dirs = set(_TIER_DIR.values())
    for index, part in enumerate(parts):
        if part == "docs" and index + 1 < len(parts) and parts[index + 1] in tier_dirs:
            return Path(*parts[:index])
    return None
