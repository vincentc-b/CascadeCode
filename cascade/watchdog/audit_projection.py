"""Versioned, bounded projection models for durable health-audit evidence.

This module is the producer boundary shared by the audit worker and projection
publisher.  It deliberately does not import the War Room: HTTP pagination and
fresh canonical re-observation belong to later consumers/producers, not to the
source-ledger decoder defined here.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.work_ids import parse_work_id_parts
from cascade.watchdog.audit_lane import canonical_audit_root

PROJECTION_SCHEMA_VERSION = 2
MAX_SOURCE_BYTES = 1024 * 1024
MAX_DETAIL_BYTES = 4096

StoreName = Literal["action_recovery", "orphan_delivery", "remediation_dispositions"]
VerificationStatus = Literal[
    "proven_incident", "verified", "pending", "stale", "unverifiable"
]

_STORE_SPECS: tuple[tuple[StoreName, str, str], ...] = (
    ("action_recovery", "executions.json", "actions"),
    ("orphan_delivery", "orphan_delivery_recoveries.json", "recoveries"),
    (
        "remediation_dispositions",
        "remediation_dispositions.json",
        "dispositions",
    ),
)
_STORE_NAMES = frozenset(spec[0] for spec in _STORE_SPECS)
_STATUSES = frozenset(VerificationStatus.__args__)
_INCIDENT_OUTCOMES = frozenset(
    {"claimed", "success", "error", "refused", "deferred", "unsafe", "no_op"}
)
_GENERATION_PREFIX = "sha256:"


def _text(value: object) -> str | None:
    return (
        value if isinstance(value, str) and value.strip() == value and value else None
    )


def _timestamp(value: object) -> str | None:
    value = _text(value)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _generation(value: object) -> str | None:
    value = _text(value)
    if value is None or not value.startswith(_GENERATION_PREFIX):
        return None
    digest = value.removeprefix(_GENERATION_PREFIX)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        return None
    return value


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Opaque identity for one recovery row or one item in its incident history."""

    store: StoreName
    row_key: str
    incident_history_ordinal: int | None = None

    def __post_init__(self) -> None:
        if self.store not in _STORE_NAMES:
            raise ValueError(f"unknown recovery store: {self.store}")
        if not _text(self.row_key) or len(self.row_key.encode()) > 1024:
            raise ValueError("source row key must be a bounded nonempty string")
        if (
            self.incident_history_ordinal is not None
            and self.incident_history_ordinal < 0
        ):
            raise ValueError("incident history ordinal must be nonnegative")

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"store": self.store, "row_key": self.row_key}
        if self.incident_history_ordinal is not None:
            result["incident_history_ordinal"] = self.incident_history_ordinal
        return result


@dataclass(frozen=True, slots=True)
class AuditSummary:
    source_ref: SourceRef | None
    work_id: str | None
    owner: str | None
    authoritative_generation: str | None
    failure_class: str | None
    occurred_at: str | None
    last_attempted_at: str | None
    last_verified_at: str | None
    verification_status: VerificationStatus
    reason: str
    fresh_until: str | None = None
    next_attempt_at: str | None = None
    detail_truncated: bool = False
    provenance: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verification_status not in _STATUSES:
            raise ValueError(f"unknown verification status: {self.verification_status}")
        if not _text(self.reason):
            raise ValueError("projection reason must be nonempty")
        for name in (
            "occurred_at",
            "last_attempted_at",
            "last_verified_at",
            "fresh_until",
            "next_attempt_at",
        ):
            value = getattr(self, name)
            if value is not None and _timestamp(value) is None:
                raise ValueError(f"{name} must be an aware ISO timestamp")
        if any(
            not _text(key) or not isinstance(value, str)
            for key, value in self.provenance.items()
        ):
            raise ValueError("projection provenance must contain string pairs")

    def as_dict(self) -> dict[str, object]:
        kind = (
            "current"
            if isinstance(self, CurrentSummary)
            else "coverage"
            if isinstance(self, CoverageSummary)
            else "history"
        )
        return {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_kind": kind,
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "work_id": self.work_id,
            "owner": self.owner,
            "authoritative_generation": self.authoritative_generation,
            "failure_class": self.failure_class,
            "occurred_at": self.occurred_at,
            "last_attempted_at": self.last_attempted_at,
            "last_verified_at": self.last_verified_at,
            "verification_status": self.verification_status,
            "reason": self.reason,
            "fresh_until": self.fresh_until,
            "next_attempt_at": self.next_attempt_at,
            "detail_truncated": self.detail_truncated,
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True, slots=True)
class CurrentSummary(AuditSummary):
    def __post_init__(self) -> None:
        super(CurrentSummary, self).__post_init__()
        if self.source_ref is None:
            raise ValueError("current rows require a source reference")
        if (
            not _text(self.work_id)
            or _generation(self.authoritative_generation) is None
        ):
            raise ValueError("current rows require unambiguous work and generation")
        if not _text(self.failure_class):
            raise ValueError("current rows require an unambiguous failure class")
        if self.verification_status != "proven_incident":
            raise ValueError("current rows must be proven incidents")


@dataclass(frozen=True, slots=True)
class CoverageSummary(AuditSummary):
    pass


@dataclass(frozen=True, slots=True)
class HistorySummary(AuditSummary):
    pass


@dataclass(frozen=True, slots=True)
class ProjectionManifest:
    epoch: str
    observed_at: str
    interval_seconds: int
    fresh_until: str
    product_identity: str
    tracking_identity: str
    page_counts: Mapping[str, int]
    source_revisions: Mapping[str, str | None] = field(default_factory=dict)
    source_failures: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not _text(self.epoch)
            or not _text(self.product_identity)
            or not _text(self.tracking_identity)
        ):
            raise ValueError("manifest epoch and repository identities are required")
        if _timestamp(self.observed_at) is None or _timestamp(self.fresh_until) is None:
            raise ValueError("manifest timestamps must be aware ISO timestamps")
        if type(self.interval_seconds) is not int or self.interval_seconds <= 0:
            raise ValueError("manifest interval must be positive")
        if set(self.page_counts) != {"current", "coverage", "history"} or any(
            type(value) is not int or value < 0 for value in self.page_counts.values()
        ):
            raise ValueError(
                "manifest page counts must cover current, coverage and history"
            )
        if any(
            name not in _STORE_NAMES
            for name in (*self.source_revisions, *self.source_failures)
        ):
            raise ValueError("manifest names an unknown recovery source")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_kind": "manifest",
            "epoch": self.epoch,
            "observed_at": self.observed_at,
            "interval_seconds": self.interval_seconds,
            "fresh_until": self.fresh_until,
            "repository_identity": {
                "product": self.product_identity,
                "tracking": self.tracking_identity,
            },
            "sections": {
                name: {"page_count": self.page_counts[name]}
                for name in ("current", "coverage", "history")
            },
            "sources": {
                name: {
                    "revision": self.source_revisions.get(name),
                    "failure": self.source_failures.get(name),
                }
                for name in sorted(_STORE_NAMES)
            },
        }


@dataclass(frozen=True, slots=True)
class RecoveryProjection:
    current: tuple[CurrentSummary, ...]
    coverage: tuple[CoverageSummary, ...]
    history: tuple[HistorySummary, ...]

    def as_dict(self) -> dict[str, list[dict[str, object]]]:
        return {
            "current": [item.as_dict() for item in self.current],
            "coverage": [item.as_dict() for item in self.coverage],
            "history": [item.as_dict() for item in self.history],
        }


def projection_root(root: Path) -> Path:
    """Return the canonical ignored publication directory."""

    return canonical_audit_root(root) / ".cascade" / "health_audit" / "projections"


def project_recovery_sources(
    root: Path,
    *,
    max_source_bytes: int = MAX_SOURCE_BYTES,
    max_detail_bytes: int = MAX_DETAIL_BYTES,
) -> RecoveryProjection:
    """Decode all recovery stores without modifying or following their files.

    A malformed row is coverage evidence for that row only.  A missing,
    malformed, non-regular, or oversized source is source-level coverage and
    cannot be mistaken for an empty healthy store.
    """

    if max_source_bytes < 1 or max_detail_bytes < 1:
        raise ValueError("projection byte limits must be positive")
    home = canonical_audit_root(root) / ".cascade"
    current: list[CurrentSummary] = []
    coverage: list[CoverageSummary] = []
    history: list[HistorySummary] = []
    for store, filename, collection in _STORE_SPECS:
        try:
            payload = _read_json_object(home / filename, max_source_bytes)
        except FileNotFoundError:
            coverage.append(_source_coverage(store, "source_missing"))
            continue
        except _SourceError as exc:
            coverage.append(_source_coverage(store, exc.reason))
            continue
        rows = payload.get(collection)
        if not isinstance(rows, Mapping):
            coverage.append(_source_coverage(store, "source_collection_malformed"))
            continue
        for raw_key, raw_row in rows.items():
            key = str(raw_key)
            try:
                ref = SourceRef(store, key)
            except ValueError:
                coverage.append(_source_coverage(store, "row_key_invalid"))
                continue
            if not isinstance(raw_row, Mapping):
                coverage.append(_row_coverage(ref, "row_malformed"))
                continue
            row = dict(raw_row)
            _project_history(row, ref, history, coverage, max_detail_bytes)
            incident = row.get("incident")
            if isinstance(incident, Mapping) and _legacy_provenance(incident):
                history.append(
                    _legacy_summary({**row, **dict(incident)}, ref, max_detail_bytes)
                )
            elif isinstance(incident, Mapping):
                item = _modern_summary(dict(incident), ref, max_detail_bytes)
                history.append(_as_history(item))
                if item.verification_status == "proven_incident":
                    current.append(item)
                elif item.verification_status == "unverifiable":
                    coverage.append(_coverage_from(item))
            elif _legacy_provenance(row):
                history.append(_legacy_summary(row, ref, max_detail_bytes))
            elif incident is not None:
                coverage.append(_row_coverage(ref, "incident_malformed"))
    current.sort(
        key=lambda item: (
            item.work_id or "",
            item.source_ref.store,
            item.source_ref.row_key,
        )
    )
    coverage.sort(key=lambda item: (_ref_key(item.source_ref), item.reason))
    history.sort(key=lambda item: (_ref_key(item.source_ref), item.occurred_at or ""))
    return RecoveryProjection(tuple(current), tuple(coverage), tuple(history))


class _SourceError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _read_json_object(path: Path, limit: int) -> dict[str, Any]:
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
        )
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise _SourceError("source_unreadable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _SourceError("source_not_regular")
        if info.st_size > limit:
            raise _SourceError("source_too_large")
        content = os.read(descriptor, limit + 1)
        if len(content) > limit:
            raise _SourceError("source_too_large")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _SourceError("source_malformed") from exc
    if not isinstance(value, dict):
        raise _SourceError("source_malformed")
    return value


def _project_history(
    row: Mapping[str, Any],
    ref: SourceRef,
    history: list[HistorySummary],
    coverage: list[CoverageSummary],
    detail_limit: int,
) -> None:
    raw = row.get("incident_history")
    if raw is None:
        return
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        coverage.append(_row_coverage(ref, "incident_history_malformed"))
        return
    for ordinal, incident in enumerate(raw):
        item_ref = SourceRef(ref.store, ref.row_key, ordinal)
        if not isinstance(incident, Mapping):
            coverage.append(_row_coverage(item_ref, "incident_history_item_malformed"))
            continue
        history.append(
            _as_history(_modern_summary(dict(incident), item_ref, detail_limit))
        )


def _modern_summary(
    incident: Mapping[str, Any], ref: SourceRef, detail_limit: int
) -> CurrentSummary | HistorySummary:
    work_id = _unambiguous_work_id(incident)
    generation = _generation(incident.get("authoritative_generation"))
    failure = _text(incident.get("failure_class"))
    owner = _text(incident.get("accountable_owner"))
    times = _summary_times(incident)
    truncated = _detail_truncated(incident, detail_limit)
    outcome = incident.get("outcome")
    if (
        work_id
        and generation
        and failure
        and outcome in _INCIDENT_OUTCOMES - {"success"}
    ):
        return CurrentSummary(
            ref,
            work_id,
            owner,
            generation,
            failure,
            *times,
            "proven_incident",
            "modern_incident_identity",
            None,
            _timestamp(incident.get("next_reassessment_at")),
            truncated,
        )
    return HistorySummary(
        ref,
        work_id,
        owner,
        generation,
        failure,
        *times,
        "unverifiable",
        "modern_identity_incomplete"
        if not (work_id and generation and failure and outcome in _INCIDENT_OUTCOMES)
        else "historical_attempt",
        None,
        _timestamp(incident.get("next_reassessment_at")),
        truncated,
    )


def _unambiguous_work_id(incident: Mapping[str, Any]) -> str | None:
    direct = _text(incident.get("work_id"))
    work = incident.get("work")
    nested = _text(work.get("work_id")) if isinstance(work, Mapping) else None
    if direct and nested and direct != nested:
        return None
    value = direct or nested
    if value is None:
        return None
    try:
        parse_work_id_parts(value)
    except Exception:
        return None
    return value


def _summary_times(
    incident: Mapping[str, Any],
) -> tuple[str | None, str | None, str | None]:
    occurred = next(
        (
            _timestamp(incident.get(name))
            for name in ("occurred_at", "created_at", "recorded_at")
            if _timestamp(incident.get(name))
        ),
        None,
    )
    attempted: list[str] = []
    successful: list[str] = []
    attempts = incident.get("attempts")
    if isinstance(attempts, Sequence) and not isinstance(
        attempts, (str, bytes, bytearray)
    ):
        for attempt in attempts:
            if not isinstance(attempt, Mapping):
                continue
            stamps = [
                _timestamp(attempt.get(name))
                for name in ("finished_at", "completed_at", "started_at", "accepted_at")
            ]
            stamp = next((value for value in stamps if value), None)
            if stamp:
                attempted.append(stamp)
                if attempt.get("outcome") in {"success", "succeeded"}:
                    successful.append(stamp)
    request = incident.get("request")
    if isinstance(request, Mapping) and (
        stamp := _timestamp(request.get("delivered_at"))
    ):
        attempted.append(stamp)
    recorded = _timestamp(incident.get("recorded_at"))
    if recorded and incident.get("outcome") == "success":
        successful.append(recorded)
    return occurred, max(attempted, default=None), max(successful, default=None)


def _legacy_provenance(row: Mapping[str, Any]) -> dict[str, str]:
    result = {}
    for name in ("child_id", "observed_child_sha", "supervisor_id"):
        if (value := _text(row.get(name))) is not None:
            result[name] = value
    if len(result) != 3:
        return {}
    # These named outer fields are the complete known legacy provenance.  Do
    # not copy arbitrary provider/result objects into the public projection.
    for name in ("action", "result", "reason"):
        if (value := _text(row.get(name))) is not None:
            result[name] = value[:512]
    return result


def _legacy_summary(
    row: Mapping[str, Any], ref: SourceRef, detail_limit: int
) -> HistorySummary:
    provenance = _legacy_provenance(row)
    occurred = next(
        (
            _timestamp(row.get(name))
            for name in ("occurred_at", "time", "created_at", "updated_at")
            if _timestamp(row.get(name))
        ),
        None,
    )
    return HistorySummary(
        ref,
        provenance.get("child_id"),
        provenance.get("supervisor_id"),
        None,
        None,
        occurred,
        occurred,
        None,
        "unverifiable",
        "legacy_identity_unverifiable",
        detail_truncated=_detail_truncated(row, detail_limit),
        provenance=provenance,
    )


def _detail_truncated(value: Mapping[str, Any], limit: int) -> bool:
    try:
        return (
            len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
            > limit
        )
    except (TypeError, ValueError):
        return True


def _as_history(item: CurrentSummary | HistorySummary) -> HistorySummary:
    values = {name: getattr(item, name) for name in AuditSummary.__dataclass_fields__}
    if isinstance(item, CurrentSummary):
        values["verification_status"] = "pending"
        values["reason"] = "current_source_attempt"
    return HistorySummary(**values)


def _coverage_from(item: AuditSummary) -> CoverageSummary:
    return CoverageSummary(
        **{name: getattr(item, name) for name in AuditSummary.__dataclass_fields__}
    )


def _source_coverage(store: StoreName, reason: str) -> CoverageSummary:
    return CoverageSummary(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "pending",
        reason,
        provenance={"store": store},
    )


def _row_coverage(ref: SourceRef, reason: str) -> CoverageSummary:
    return CoverageSummary(
        ref, None, None, None, None, None, None, None, "unverifiable", reason
    )


def _ref_key(ref: SourceRef | None) -> tuple[str, str, int]:
    if ref is None:
        return ("", "", -1)
    return (
        ref.store,
        ref.row_key,
        ref.incident_history_ordinal
        if ref.incident_history_ordinal is not None
        else -1,
    )


def projection_json_schema() -> dict[str, object]:
    """Return the single schema document used by all projection artifacts."""

    nullable_string = {"type": ["string", "null"]}
    source_ref_object = {
        "type": "object",
        "properties": {
            "store": {"enum": sorted(_STORE_NAMES)},
            "row_key": {"type": "string", "minLength": 1, "maxLength": 1024},
            "incident_history_ordinal": {"type": "integer", "minimum": 0},
        },
        "required": ["store", "row_key"],
        "additionalProperties": False,
    }
    source_ref = {"anyOf": [source_ref_object, {"type": "null"}]}
    summary_properties = {
        "schema_version": {"const": PROJECTION_SCHEMA_VERSION},
        "projection_kind": {"enum": ["current", "coverage", "history"]},
        "source_ref": source_ref,
        "work_id": nullable_string,
        "owner": nullable_string,
        "authoritative_generation": nullable_string,
        "failure_class": nullable_string,
        "occurred_at": nullable_string,
        "last_attempted_at": nullable_string,
        "last_verified_at": nullable_string,
        "verification_status": {"enum": sorted(_STATUSES)},
        "reason": {"type": "string", "minLength": 1},
        "fresh_until": nullable_string,
        "next_attempt_at": nullable_string,
        "detail_truncated": {"type": "boolean"},
        "provenance": {"type": "object", "additionalProperties": {"type": "string"}},
    }
    required = list(summary_properties)

    def summary_schema(kind: str) -> dict[str, object]:
        properties = dict(summary_properties)
        properties["projection_kind"] = {"const": kind}
        if kind == "current":
            properties.update(
                source_ref=source_ref_object,
                work_id={"type": "string", "minLength": 1},
                authoritative_generation={
                    "type": "string",
                    "pattern": "^sha256:[0-9a-f]{64}$",
                },
                failure_class={"type": "string", "minLength": 1},
                verification_status={"const": "proven_incident"},
            )
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "cascade://health-audit/projection/v2",
        "title": "Cascade health audit projection",
        "oneOf": [
            {"$ref": "#/$defs/manifest"},
            {"$ref": "#/$defs/current"},
            {"$ref": "#/$defs/coverage"},
            {"$ref": "#/$defs/history"},
        ],
        "$defs": {
            "manifest": {
                "type": "object",
                "properties": {
                    "schema_version": {"const": PROJECTION_SCHEMA_VERSION},
                    "projection_kind": {"const": "manifest"},
                    "epoch": {"type": "string", "minLength": 1},
                    "observed_at": {"type": "string"},
                    "interval_seconds": {"type": "integer", "minimum": 1},
                    "fresh_until": {"type": "string"},
                    "repository_identity": {"type": "object"},
                    "sections": {"type": "object"},
                    "sources": {"type": "object"},
                },
                "required": [
                    "schema_version",
                    "projection_kind",
                    "epoch",
                    "observed_at",
                    "interval_seconds",
                    "fresh_until",
                    "repository_identity",
                    "sections",
                    "sources",
                ],
                "additionalProperties": False,
            },
            "current": summary_schema("current"),
            "coverage": summary_schema("coverage"),
            "history": summary_schema("history"),
        },
    }


__all__ = [
    "PROJECTION_SCHEMA_VERSION",
    "MAX_SOURCE_BYTES",
    "MAX_DETAIL_BYTES",
    "SourceRef",
    "AuditSummary",
    "CurrentSummary",
    "CoverageSummary",
    "HistorySummary",
    "ProjectionManifest",
    "RecoveryProjection",
    "projection_root",
    "project_recovery_sources",
    "projection_json_schema",
]
