"""Canonical hierarchical work identifiers: parse, format, validate, allocate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from cascade.board.errors import SchemaError
from cascade.board.id_reservations import reserve_work_id, reserved_work_ids
from cascade.board.types import BoardIndex, WorkId, WorkTier

_SEGMENT = r"[0-9]{3}"
_EPIC_RE = re.compile(rf"^epic_({_SEGMENT})$")
_LEGACY_FEATURE_RE = re.compile(rf"^feat_({_SEGMENT})$")
_HIER_FEATURE_RE = re.compile(rf"^feat_({_SEGMENT})_({_SEGMENT})$")
_LEGACY_TASK_RE = re.compile(rf"^task_({_SEGMENT})$")
_HIER_TASK_RE = re.compile(rf"^task_({_SEGMENT})_({_SEGMENT})_({_SEGMENT})$")
_FILENAME_PREFIX_RE = re.compile(
    r"^(?:"
    rf"epic_{_SEGMENT}|"
    rf"feat_{_SEGMENT}(?:_{_SEGMENT})?|"
    rf"task_{_SEGMENT}(?:_{_SEGMENT}_{_SEGMENT})?"
    r")"
)

WorkIdForm = Literal["legacy", "hierarchical"]


@dataclass(frozen=True, slots=True)
class ParsedWorkId:
    tier: WorkTier
    segments: tuple[int, ...]
    form: WorkIdForm


def filename_work_id_prefix(stem: str) -> str | None:
    """Return the work-id prefix at the start of a filename stem, if any."""

    match = _FILENAME_PREFIX_RE.match(stem)
    if match is None:
        return None
    return match.group(0)


def parse_work_id_parts(value: str) -> ParsedWorkId:
    """Parse a legacy or hierarchical work id. Raises SchemaError when malformed."""

    match = _EPIC_RE.fullmatch(value)
    if match is not None:
        segment = _segment_int(match.group(1), value)
        return ParsedWorkId(tier="epic", segments=(segment,), form="legacy")

    match = _HIER_FEATURE_RE.fullmatch(value)
    if match is not None:
        epic_num = _segment_int(match.group(1), value)
        feature_num = _segment_int(match.group(2), value)
        return ParsedWorkId(
            tier="feature",
            segments=(epic_num, feature_num),
            form="hierarchical",
        )

    match = _LEGACY_FEATURE_RE.fullmatch(value)
    if match is not None:
        segment = _segment_int(match.group(1), value)
        return ParsedWorkId(tier="feature", segments=(segment,), form="legacy")

    match = _HIER_TASK_RE.fullmatch(value)
    if match is not None:
        epic_num = _segment_int(match.group(1), value)
        feature_num = _segment_int(match.group(2), value, allow_zero=True)
        task_num = _segment_int(match.group(3), value)
        return ParsedWorkId(
            tier="task",
            segments=(epic_num, feature_num, task_num),
            form="hierarchical",
        )

    match = _LEGACY_TASK_RE.fullmatch(value)
    if match is not None:
        segment = _segment_int(match.group(1), value)
        return ParsedWorkId(tier="task", segments=(segment,), form="legacy")

    raise SchemaError(f"invalid work id: {value!r}")


def tier_of_work_id(value: str) -> WorkTier:
    """Return the tier encoded in ``value`` without validating parent links."""

    return parse_work_id_parts(value).tier


def format_hierarchical_epic_id(epic_num: int) -> str:
    return _format_segments("epic", (epic_num,))


def format_hierarchical_feature_id(epic_num: int, feature_num: int) -> str:
    return _format_segments("feature", (epic_num, feature_num))


def format_hierarchical_task_id(epic_num: int, feature_num: int, task_num: int) -> str:
    if task_num < 1 or task_num > 999:
        raise SchemaError("work id segment must be between 001 and 999")
    if epic_num < 1 or epic_num > 999:
        raise SchemaError("work id segment must be between 001 and 999")
    if feature_num < 0 or feature_num > 999:
        raise SchemaError("invalid task feature segment")
    return f"task_{epic_num:03d}_{feature_num:03d}_{task_num:03d}"


def feature_id_key(feature_id: str) -> tuple[int, int]:
    """Segments that prefix tasks minted under ``feature_id``."""

    parsed = parse_work_id_parts(feature_id)
    if parsed.tier != "feature":
        raise SchemaError(f"{feature_id!r} is not a feature id")
    if parsed.form == "legacy":
        return parsed.segments[0], 0
    return parsed.segments[0], parsed.segments[1]


def validate_work_id_identity(
    work_id: str,
    *,
    tier: WorkTier,
    parent: str | None,
) -> None:
    """Reject malformed ids and parent/segment disagreement for hierarchical forms."""

    parsed = parse_work_id_parts(work_id)
    if parsed.tier != tier:
        raise SchemaError(f"id {work_id} does not match tier {tier}")

    if parsed.form == "legacy":
        return

    if tier == "feature":
        if parent is None:
            raise SchemaError(f"{work_id} requires a parent")
        expected_parent = format_hierarchical_epic_id(parsed.segments[0])
        if parent != expected_parent:
            raise SchemaError(
                f"{work_id} parent {parent!r} does not match epic segment epic_{parsed.segments[0]:03d}"
            )
        return

    if tier == "task":
        if parent is None:
            raise SchemaError(f"{work_id} requires a parent")
        epic_num, feature_num = parsed.segments[0], parsed.segments[1]
        parent_key = feature_id_key(parent)
        if parent_key != (epic_num, feature_num):
            raise SchemaError(
                f"{work_id} segments do not match parent feature {parent!r}"
            )


def allocate_hierarchical_id(
    tier: WorkTier,
    board: BoardIndex,
    *,
    parent_id: str | None = None,
) -> WorkId:
    """Next canonical hierarchical id for ``tier`` scoped to ``parent_id`` when required."""

    if tier == "epic":
        if parent_id is not None:
            raise SchemaError("epic ids cannot have a parent")
        return _allocate_epic_id(board)

    if tier == "feature":
        if parent_id is None:
            raise SchemaError("feature ids require a parent epic")
        return _allocate_feature_id(board, parent_id)

    if tier == "task":
        if parent_id is None:
            raise SchemaError("task ids require a parent feature")
        return _allocate_task_id(board, parent_id)

    raise SchemaError(f"unknown tier: {tier!r}")


def _allocate_epic_id(board: BoardIndex) -> WorkId:
    used = _occupied_epic_numbers(board)
    epic_num = (max(used, default=0)) + 1
    work_id = format_hierarchical_epic_id(epic_num)
    _ensure_free(work_id, board)
    reserve_work_id(work_id)
    return work_id


def _allocate_feature_id(board: BoardIndex, epic_id: str) -> WorkId:
    epic_parsed = parse_work_id_parts(epic_id)
    if epic_parsed.tier != "epic":
        raise SchemaError(f"parent {epic_id!r} is not an epic")
    epic_num = epic_parsed.segments[0]
    used = _occupied_feature_numbers(board, epic_id, epic_num)
    feature_num = (max(used, default=0)) + 1
    work_id = format_hierarchical_feature_id(epic_num, feature_num)
    _ensure_free(work_id, board)
    reserve_work_id(work_id)
    return work_id


def _allocate_task_id(board: BoardIndex, feature_id: str) -> WorkId:
    feature_parsed = parse_work_id_parts(feature_id)
    if feature_parsed.tier != "feature":
        raise SchemaError(f"parent {feature_id!r} is not a feature")
    epic_num, feature_num = feature_id_key(feature_id)
    used = _occupied_task_numbers(board, feature_id, epic_num, feature_num)
    task_num = (max(used, default=0)) + 1
    work_id = format_hierarchical_task_id(epic_num, feature_num, task_num)
    _ensure_free(work_id, board)
    reserve_work_id(work_id)
    return work_id


def _occupied_epic_numbers(board: BoardIndex) -> set[int]:
    used: set[int] = set()
    for work_id in board.by_id:
        try:
            parsed = parse_work_id_parts(work_id)
        except SchemaError:
            continue
        if parsed.tier == "epic":
            used.add(parsed.segments[0])
    return used


def _occupied_feature_numbers(board: BoardIndex, epic_id: str, epic_num: int) -> set[int]:
    used: set[int] = set()
    for work_id, meta in board.by_id.items():
        if meta.tier != "feature" or meta.parent != epic_id:
            continue
        parsed = parse_work_id_parts(work_id)
        if parsed.form == "hierarchical":
            if parsed.segments[0] != epic_num:
                continue
            used.add(parsed.segments[1])
        else:
            used.add(parsed.segments[0])
    return used


def _occupied_task_numbers(
    board: BoardIndex,
    feature_id: str,
    epic_num: int,
    feature_num: int,
) -> set[int]:
    used: set[int] = set()
    for work_id, meta in board.by_id.items():
        if meta.tier != "task" or meta.parent != feature_id:
            continue
        parsed = parse_work_id_parts(work_id)
        if parsed.form == "hierarchical":
            if parsed.segments[0] != epic_num or parsed.segments[1] != feature_num:
                continue
            used.add(parsed.segments[2])
        else:
            used.add(parsed.segments[0])
    return used


def _ensure_free(work_id: WorkId, board: BoardIndex) -> None:
    if work_id in board.by_id or work_id in reserved_work_ids():
        raise SchemaError(f"id collision: {work_id}")


def _format_segments(tier: WorkTier, segments: tuple[int, ...]) -> str:
    prefix = {"epic": "epic", "feature": "feat", "task": "task"}[tier]
    for segment in segments:
        if segment < 1 or segment > 999:
            raise SchemaError("work id segment must be between 001 and 999")
    return prefix + "".join(f"_{segment:03d}" for segment in segments)


def _segment_int(raw: str, work_id: str, *, allow_zero: bool = False) -> int:
    value = int(raw, 10)
    if value < 0 or (value == 0 and not allow_zero):
        raise SchemaError(f"invalid work id: {work_id!r}")
    if value > 999:
        raise SchemaError(f"invalid work id: {work_id!r}")
    return value
