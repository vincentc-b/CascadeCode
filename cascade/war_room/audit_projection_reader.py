"""Bounded, epoch-pinned consumer for published health-audit projections.

This module deliberately does not use ``read_projection_manifest``: that function
is a producer-side full-epoch integrity check and visits every retained page.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping

from cascade.board.work_ids import parse_work_id_parts
from cascade.watchdog.audit_projection import (
    MAX_AGGREGATE_REASONS,
    MAX_MANIFEST_BYTES,
    MAX_PAGE_BYTES,
    MAX_PAGE_ROWS,
    PROJECTION_SCHEMA_VERSION,
    AuditSummary,
    CoverageSummary,
    CurrentSummary,
    HistorySummary,
    SourceRef,
    projection_repository_identities,
    projection_root,
)

MAX_REQUEST_READ_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_MANIFEST_PAGES = 100_000
DEFAULT_PAGE_ROWS = 50

Section = Literal["current", "coverage", "history"]
_SECTIONS = ("current", "coverage", "history")
_STATUSES = frozenset(
    {"proven_incident", "verified", "pending", "stale", "unverifiable"}
)
_STORES = frozenset(
    {"action_recovery", "orphan_delivery", "remediation_dispositions"}
)
_ROW_TYPES = {
    "current": CurrentSummary,
    "coverage": CoverageSummary,
    "history": HistorySummary,
}
_ROW_FIELDS = frozenset(
    {
        "schema_version",
        "projection_kind",
        "source_ref",
        *AuditSummary.__dataclass_fields__,
    }
)


class AuditProjectionRequestError(ValueError):
    """The caller supplied an invalid filter, limit, or cursor."""


class _ReadError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AuditPageRequest:
    """One bounded section request.

    String filters are exact after surrounding whitespace and UTC timestamp
    normalization. Unknown row fields never satisfy a filter.
    """

    section: Section
    cursor: str | None = None
    limit: int = DEFAULT_PAGE_ROWS
    work_id: str | None = None
    owner: str | None = None
    status: str | None = None
    occurred_from: str | datetime | None = None
    occurred_to: str | datetime | None = None


@dataclass(slots=True)
class _Budget:
    remaining: int = MAX_REQUEST_READ_BYTES
    read: int = 0


def read_audit_snapshot_header(
    root: Path,
    *,
    now: datetime | None = None,
    product_identity: str | None = None,
    tracking_identity: str | None = None,
) -> dict[str, object]:
    """Read only the pointer and its manifest, returning ready or pending."""

    budget = _Budget()
    return _read_header(
        root,
        budget,
        now=now,
        product_identity=product_identity,
        tracking_identity=tracking_identity,
    )


def read_audit_projection(
    root: Path,
    request: AuditPageRequest,
    *,
    now: datetime | None = None,
    product_identity: str | None = None,
    tracking_identity: str | None = None,
) -> dict[str, object]:
    """Read a bounded page from the current immutable projection epoch."""

    normalized = _normalize_request(request)
    decoded_cursor: dict[str, object] | None = None
    if request.cursor is not None:
        decoded_cursor = _decode_cursor(request.cursor)
        if (
            decoded_cursor["section"] != request.section
            or decoded_cursor["filters"] != normalized
        ):
            raise AuditProjectionRequestError("cursor does not match request")
    budget = _Budget()
    header_state = _read_header(
        root,
        budget,
        now=now,
        product_identity=product_identity,
        tracking_identity=tracking_identity,
    )
    if header_state.get("state") != "ready":
        return header_state
    header = header_state["header"]
    assert isinstance(header, dict)
    epoch = str(header["epoch"])

    position = (0, 0)
    if decoded_cursor is not None:
        if decoded_cursor["epoch"] != epoch:
            return {
                "state": "pending",
                "reason": "epoch_changed",
                "restart": True,
                "epoch": epoch,
                "previous_epoch": decoded_cursor["epoch"],
                "last_observed_at": header["observed_at"],
            }
        position = (int(decoded_cursor["page"]), int(decoded_cursor["row"]))

    sections = header["sections"]
    assert isinstance(sections, dict)
    section_header = sections[request.section]
    assert isinstance(section_header, dict)
    page_count = int(section_header["page_count"])
    if position[0] > page_count or (position[0] == page_count and position[1]):
        raise AuditProjectionRequestError("cursor offset is outside the section")

    rows: list[dict[str, object]] = []
    scanned = 0
    page_index, row_index = position
    reason: str | None = None
    base = projection_root(root)
    while page_index < page_count:
        loaded_page = page_index
        page_path = base / epoch / request.section / f"{page_index:06d}.json"
        try:
            page = _read_json(page_path, MAX_PAGE_BYTES, budget)
        except FileNotFoundError:
            return _pending("page_missing", epoch, header)
        except _ReadError as exc:
            if exc.reason == "read_budget":
                reason = "read_budget"
                break
            return _pending(f"page_{exc.reason}", epoch, header)
        page_rows = _validate_page(page, request.section, epoch)
        if page_rows is None:
            return _pending("page_incompatible", epoch, header)
        if row_index > len(page_rows):
            raise AuditProjectionRequestError("cursor row offset is outside the page")
        while row_index < len(page_rows):
            row = page_rows[row_index]
            scanned += 1
            if _matches(row, normalized):
                candidate = rows + [row]
                result = _ready_result(
                    header,
                    request.section,
                    candidate,
                    None,
                    scanned,
                    budget.read,
                    complete=False,
                    reason="response_budget",
                )
                if len(_json_bytes(result)) > MAX_RESPONSE_BYTES:
                    reason = "response_budget"
                    break
                rows = candidate
                row_index += 1
                if len(rows) == request.limit:
                    reason = "limit"
                    break
            else:
                row_index += 1
        if reason is not None:
            if row_index >= len(page_rows):
                page_index = loaded_page + 1
                row_index = 0
            break
        page_index = loaded_page + 1
        row_index = 0

    complete = page_index >= page_count
    next_cursor = None
    if not complete:
        next_cursor = _encode_cursor(
            request.section, epoch, normalized, page_index, row_index
        )
    result = _ready_result(
        header,
        request.section,
        rows,
        next_cursor,
        scanned,
        budget.read,
        complete=complete,
        reason=None if complete else reason or "continuation",
    )
    if len(_json_bytes(result)) > MAX_RESPONSE_BYTES:
        # Header validation caps aggregate size, so this can only be reached by
        # a single projection row which cannot safely be represented.
        return _pending("row_too_large", epoch, header)
    return result


read_audit_page = read_audit_projection


def _normalize_request(request: AuditPageRequest) -> dict[str, str | None]:
    if request.section not in _SECTIONS:
        raise AuditProjectionRequestError("unknown audit section")
    if type(request.limit) is not int or not 1 <= request.limit <= MAX_PAGE_ROWS:
        raise AuditProjectionRequestError("limit must be from 1 through 100")
    work_id = _filter_text(request.work_id, "work_id")
    if work_id is not None:
        try:
            parse_work_id_parts(work_id)
        except Exception as exc:
            raise AuditProjectionRequestError("work_id filter is invalid") from exc
    owner = _filter_text(request.owner, "owner", maximum=512)
    status = _filter_text(request.status, "status")
    if status is not None and status not in _STATUSES:
        raise AuditProjectionRequestError("status filter is invalid")
    occurred_from = _filter_timestamp(request.occurred_from, "occurred_from")
    occurred_to = _filter_timestamp(request.occurred_to, "occurred_to")
    if occurred_from and occurred_to and occurred_from > occurred_to:
        raise AuditProjectionRequestError("occurrence time range is inverted")
    return {
        "work_id": work_id,
        "owner": owner,
        "status": status,
        "occurred_from": occurred_from.isoformat() if occurred_from else None,
        "occurred_to": occurred_to.isoformat() if occurred_to else None,
    }


def _filter_text(
    value: object, name: str, *, maximum: int = 256
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip().encode()) > maximum:
        raise AuditProjectionRequestError(f"{name} filter is invalid")
    return value.strip()


def _filter_timestamp(value: object, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise AuditProjectionRequestError(f"{name} filter is invalid") from exc
    if parsed.tzinfo is None:
        raise AuditProjectionRequestError(f"{name} filter must include a timezone")
    return parsed.astimezone(timezone.utc)


def _read_header(
    root: Path,
    budget: _Budget,
    *,
    now: datetime | None,
    product_identity: str | None,
    tracking_identity: str | None,
) -> dict[str, object]:
    base = projection_root(root)
    try:
        pointer = _read_json(base / "current.json", MAX_MANIFEST_BYTES, budget)
    except FileNotFoundError:
        return {"state": "pending", "reason": "pointer_missing"}
    except _ReadError as exc:
        return {"state": "pending", "reason": f"pointer_{exc.reason}"}
    epoch = pointer.get("epoch")
    if (
        set(pointer) != {"schema_version", "epoch"}
        or pointer.get("schema_version") != PROJECTION_SCHEMA_VERSION
        or not isinstance(epoch, str)
        or not epoch
        or len(epoch) > 128
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in epoch)
    ):
        return {"state": "pending", "reason": "pointer_incompatible"}
    try:
        manifest = _read_json(base / epoch / "manifest.json", MAX_MANIFEST_BYTES, budget)
    except FileNotFoundError:
        return {"state": "pending", "reason": "manifest_missing", "epoch": epoch}
    except _ReadError as exc:
        return {"state": "pending", "reason": f"manifest_{exc.reason}", "epoch": epoch}
    header = _validate_manifest(manifest, epoch)
    if header is None:
        return {"state": "pending", "reason": "manifest_incompatible", "epoch": epoch}
    expected_product, expected_tracking = projection_repository_identities(root)
    if product_identity is not None:
        expected_product = product_identity
    if tracking_identity is not None:
        expected_tracking = tracking_identity
    identity = header["repository_identity"]
    assert isinstance(identity, dict)
    if identity != {"product": expected_product, "tracking": expected_tracking}:
        return {
            "state": "pending",
            "reason": "repository_identity_mismatch",
            "epoch": epoch,
            "last_observed_at": header["observed_at"],
        }
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fresh_until = datetime.fromisoformat(str(header["fresh_until"]))
    if moment >= fresh_until:
        return {
            "state": "pending",
            "reason": "snapshot_stale",
            "epoch": epoch,
            "last_observed_at": header["observed_at"],
            "fresh_until": header["fresh_until"],
        }
    header["read_bytes"] = budget.read
    return {"state": "ready", "header": header}


def _validate_manifest(
    manifest: Mapping[str, object], epoch: str
) -> dict[str, object] | None:
    required = {
        "schema_version",
        "projection_kind",
        "epoch",
        "observed_at",
        "interval_seconds",
        "fresh_until",
        "repository_identity",
        "sections",
        "coverage_aggregates",
        "sources",
    }
    if set(manifest) != required or (
        manifest.get("schema_version") != PROJECTION_SCHEMA_VERSION
        or manifest.get("projection_kind") != "manifest"
        or manifest.get("epoch") != epoch
    ):
        return None
    observed = _aware_timestamp(manifest.get("observed_at"))
    fresh = _aware_timestamp(manifest.get("fresh_until"))
    interval = manifest.get("interval_seconds")
    identity = manifest.get("repository_identity")
    if (
        observed is None
        or fresh is None
        or fresh < observed
        or type(interval) is not int
        or interval <= 0
        or not isinstance(identity, dict)
        or set(identity) != {"product", "tracking"}
        or any(not isinstance(value, str) or not value for value in identity.values())
    ):
        return None
    sections = manifest.get("sections")
    if not isinstance(sections, dict) or set(sections) != set(_SECTIONS):
        return None
    clean_sections: dict[str, dict[str, int]] = {}
    for name in _SECTIONS:
        value = sections[name]
        if not isinstance(value, dict) or set(value) != {"page_count", "row_count"}:
            return None
        pages, rows = value.get("page_count"), value.get("row_count")
        if (
            type(pages) is not int
            or type(rows) is not int
            or not 0 <= pages <= MAX_MANIFEST_PAGES
            or rows < 0
            or (pages == 0) != (rows == 0)
            or rows > pages * MAX_PAGE_ROWS
            or (pages and rows < pages)
        ):
            return None
        clean_sections[name] = {"page_count": pages, "row_count": rows}
    aggregates = _validate_aggregates(
        manifest.get("coverage_aggregates"), clean_sections["coverage"]["row_count"]
    )
    sources = manifest.get("sources")
    if (
        aggregates is None
        or not isinstance(sources, dict)
        or set(sources) != _STORES
        or any(
            not isinstance(source, dict)
            or set(source) != {"revision", "failure"}
            or any(
                value is not None and not isinstance(value, str)
                for value in source.values()
            )
            for source in sources.values()
        )
    ):
        return None
    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "epoch": epoch,
        "observed_at": observed.isoformat(),
        "fresh_until": fresh.isoformat(),
        "interval_seconds": interval,
        "repository_identity": dict(identity),
        "sections": clean_sections,
        "coverage_aggregates": aggregates,
    }


def _validate_aggregates(value: object, total: int) -> dict[str, object] | None:
    if not isinstance(value, dict) or set(value) != {"by_status", "by_reason", "other_reasons"}:
        return None
    statuses, reasons, other = value.get("by_status"), value.get("by_reason"), value.get("other_reasons")
    if (
        not isinstance(statuses, dict)
        or set(statuses) - _STATUSES
        or any(type(count) is not int or count < 0 for count in statuses.values())
        or sum(statuses.values()) != total
        or not isinstance(reasons, dict)
        or len(reasons) > MAX_AGGREGATE_REASONS
        or any(not isinstance(reason, str) or not reason or len(reason.encode()) > 512 for reason in reasons)
        or any(type(count) is not int or count < 0 for count in reasons.values())
        or type(other) is not int
        or other < 0
        or sum(reasons.values()) + other != total
    ):
        return None
    return {"by_status": dict(statuses), "by_reason": dict(reasons), "other_reasons": other}


def _validate_page(
    page: Mapping[str, object], section: str, epoch: str
) -> list[dict[str, object]] | None:
    if set(page) != {"schema_version", "projection_kind", "epoch", "rows"} or (
        page.get("schema_version") != PROJECTION_SCHEMA_VERSION
        or page.get("projection_kind") != section
        or page.get("epoch") != epoch
    ):
        return None
    rows = page.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PAGE_ROWS:
        return None
    if any(not isinstance(row, dict) or not _validate_row(row, section) for row in rows):
        return None
    return rows


def _validate_row(row: Mapping[str, object], section: str) -> bool:
    if set(row) != _ROW_FIELDS or row.get("schema_version") != PROJECTION_SCHEMA_VERSION or row.get("projection_kind") != section:
        return False
    ref_raw = row.get("source_ref")
    try:
        ref = None
        if isinstance(ref_raw, dict):
            if set(ref_raw) not in ({"store", "row_key"}, {"store", "row_key", "incident_history_ordinal"}):
                return False
            if (
                not isinstance(ref_raw.get("store"), str)
                or not isinstance(ref_raw.get("row_key"), str)
                or (
                    "incident_history_ordinal" in ref_raw
                    and type(ref_raw.get("incident_history_ordinal")) is not int
                )
            ):
                return False
            ref = SourceRef(
                ref_raw.get("store"),  # type: ignore[arg-type]
                ref_raw.get("row_key"),  # type: ignore[arg-type]
                ref_raw.get("incident_history_ordinal"),  # type: ignore[arg-type]
            )
        elif ref_raw is not None:
            return False
        nullable_strings = (
            "work_id",
            "owner",
            "authoritative_generation",
            "failure_class",
            "occurred_at",
            "last_attempted_at",
            "last_verified_at",
            "fresh_until",
            "next_attempt_at",
        )
        if any(
            row.get(name) is not None and not isinstance(row.get(name), str)
            for name in nullable_strings
        ):
            return False
        provenance = row.get("provenance")
        if (
            type(row.get("detail_truncated")) is not bool
            or not isinstance(provenance, dict)
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or len(key.encode()) > 512
                or len(value.encode()) > 4096
                for key, value in provenance.items()
            )
        ):
            return False
        values = {name: row.get(name) for name in AuditSummary.__dataclass_fields__}
        values["source_ref"] = ref
        _ROW_TYPES[section](**values)
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _read_json(path: Path, limit: int, budget: _Budget) -> dict[str, object]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise _ReadError("unreadable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _ReadError("not_regular")
        if info.st_size > limit:
            raise _ReadError("too_large")
        if info.st_size > budget.remaining:
            raise _ReadError("read_budget")
        allowance = budget.remaining
        content = os.read(descriptor, min(limit, allowance))
        final_info = os.fstat(descriptor)
        if final_info.st_size > limit:
            raise _ReadError("too_large")
        if final_info.st_size > allowance:
            raise _ReadError("read_budget")
        budget.remaining -= len(content)
        budget.read += len(content)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _ReadError("malformed") from exc
    if not isinstance(value, dict):
        raise _ReadError("malformed")
    return value


def _aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _matches(row: Mapping[str, object], filters: Mapping[str, str | None]) -> bool:
    for field in ("work_id", "owner"):
        if filters[field] is not None and row.get(field) != filters[field]:
            return False
    if filters["status"] is not None and row.get("verification_status") != filters["status"]:
        return False
    if filters["occurred_from"] is not None or filters["occurred_to"] is not None:
        occurred = _aware_timestamp(row.get("occurred_at"))
        if occurred is None:
            return False
        if filters["occurred_from"] is not None and occurred < datetime.fromisoformat(filters["occurred_from"]):
            return False
        if filters["occurred_to"] is not None and occurred > datetime.fromisoformat(filters["occurred_to"]):
            return False
    return True


def _ready_result(
    header: dict[str, object],
    section: str,
    rows: list[dict[str, object]],
    cursor: str | None,
    scanned: int,
    read_bytes: int,
    *,
    complete: bool,
    reason: str | None,
) -> dict[str, object]:
    page = {
        "epoch": header["epoch"],
        "section": section,
        "rows": rows,
        "next_cursor": cursor,
        "scanned": scanned,
        "returned": len(rows),
        "complete": complete,
        "truncated": not complete,
        "reason": reason,
        "read_bytes": read_bytes,
    }
    return {"state": "ready", "header": header, "page": page}


def _pending(reason: str, epoch: str, header: Mapping[str, object]) -> dict[str, object]:
    return {
        "state": "pending",
        "reason": reason,
        "epoch": epoch,
        "last_observed_at": header.get("observed_at"),
    }


def _encode_cursor(
    section: str,
    epoch: str,
    filters: Mapping[str, str | None],
    page: int,
    row: int,
) -> str:
    payload = {"v": 1, "section": section, "epoch": epoch, "filters": filters, "page": page, "row": row}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    envelope = {"payload": payload, "digest": hashlib.sha256(canonical).hexdigest()}
    return base64.urlsafe_b64encode(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=").decode()


def _decode_cursor(value: str) -> dict[str, object]:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise AuditProjectionRequestError("cursor is malformed")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        envelope = json.loads(raw)
        payload = envelope["payload"]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AuditProjectionRequestError("cursor is malformed") from exc
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"payload", "digest"}
        or envelope.get("digest") != hashlib.sha256(canonical).hexdigest()
        or not isinstance(payload, dict)
        or set(payload) != {"v", "section", "epoch", "filters", "page", "row"}
        or payload.get("v") != 1
        or payload.get("section") not in _SECTIONS
        or not isinstance(payload.get("epoch"), str)
        or not isinstance(payload.get("filters"), dict)
        or set(payload.get("filters", {}))
        != {"work_id", "owner", "status", "occurred_from", "occurred_to"}
        or any(
            item is not None and not isinstance(item, str)
            for item in payload.get("filters", {}).values()
        )
        or type(payload.get("page")) is not int
        or type(payload.get("row")) is not int
        or payload["page"] < 0
        or payload["row"] < 0
    ):
        raise AuditProjectionRequestError("cursor is malformed")
    return payload


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


__all__ = [
    "AuditPageRequest",
    "AuditProjectionRequestError",
    "DEFAULT_PAGE_ROWS",
    "MAX_REQUEST_READ_BYTES",
    "MAX_RESPONSE_BYTES",
    "read_audit_page",
    "read_audit_projection",
    "read_audit_snapshot_header",
]
