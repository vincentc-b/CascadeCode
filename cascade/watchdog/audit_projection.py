"""Versioned, bounded projection models for durable health-audit evidence.

This module is the producer boundary shared by the audit worker and projection
publisher.  It deliberately does not import the War Room: HTTP pagination and
fresh canonical re-observation belong to later consumers/producers, not to the
source-ledger decoder defined here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.work_ids import parse_work_id_parts
from cascade.watchdog.audit_lane import canonical_audit_root

PROJECTION_SCHEMA_VERSION = 2
MAX_SOURCE_BYTES = 1024 * 1024
MAX_DETAIL_BYTES = 4096
MAX_PAGE_ROWS = 100
MAX_PAGE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_AGGREGATE_REASONS = 64
_EPOCH_RE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")

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


def _bounded_reason(value: object) -> str:
    reason = str(value)
    encoded = reason.encode()
    if len(encoded) <= 512:
        return reason
    return encoded[:512].decode("utf-8", errors="ignore")


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
        if not _text(self.reason) or len(self.reason.encode()) > 512:
            raise ValueError("projection reason must be a bounded nonempty string")
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
    row_counts: Mapping[str, int]
    coverage_by_status: Mapping[str, int] = field(default_factory=dict)
    coverage_by_reason: Mapping[str, int] = field(default_factory=dict)
    coverage_other_reasons: int = 0
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
        if set(self.row_counts) != {"current", "coverage", "history"} or any(
            type(value) is not int or value < 0 for value in self.row_counts.values()
        ):
            raise ValueError(
                "manifest row counts must cover current, coverage and history"
            )
        for name in self.page_counts:
            pages = self.page_counts[name]
            rows = self.row_counts[name]
            if (
                (pages == 0) != (rows == 0)
                or rows > pages * MAX_PAGE_ROWS
                or (pages and rows < pages)
            ):
                raise ValueError("manifest page and row counts are inconsistent")
        if (
            set(self.coverage_by_status) - _STATUSES
            or any(type(value) is not int or value < 0 for value in self.coverage_by_status.values())
            or sum(self.coverage_by_status.values()) != self.row_counts["coverage"]
        ):
            raise ValueError("manifest coverage status aggregate is invalid")
        if (
            len(self.coverage_by_reason) > MAX_AGGREGATE_REASONS
            or any(not _text(key) or len(key.encode()) > 512 for key in self.coverage_by_reason)
            or any(type(value) is not int or value < 0 for value in self.coverage_by_reason.values())
            or type(self.coverage_other_reasons) is not int
            or self.coverage_other_reasons < 0
            or sum(self.coverage_by_reason.values()) + self.coverage_other_reasons
            != self.row_counts["coverage"]
        ):
            raise ValueError("manifest coverage reason aggregate is invalid")
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
                name: {
                    "page_count": self.page_counts[name],
                    "row_count": self.row_counts[name],
                }
                for name in ("current", "coverage", "history")
            },
            "coverage_aggregates": {
                "by_status": dict(sorted(self.coverage_by_status.items())),
                "by_reason": dict(sorted(self.coverage_by_reason.items())),
                "other_reasons": self.coverage_other_reasons,
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


def read_projection_manifest(root: Path) -> dict[str, object]:
    """Read and pin one complete schema-2 epoch, or return pending state."""

    base = projection_root(root)
    try:
        pointer = _read_json_object(base / "current.json", MAX_MANIFEST_BYTES)
    except FileNotFoundError:
        return {"status": "pending", "reason": "pointer_missing"}
    except _SourceError as exc:
        return {"status": "pending", "reason": f"pointer_{exc.reason}"}
    epoch = pointer.get("epoch")
    if (
        pointer.get("schema_version") != PROJECTION_SCHEMA_VERSION
        or not isinstance(epoch, str)
        or _EPOCH_RE.fullmatch(epoch) is None
    ):
        return {"status": "pending", "reason": "pointer_incompatible"}
    try:
        manifest = _read_json_object(base / epoch / "manifest.json", MAX_MANIFEST_BYTES)
    except FileNotFoundError:
        return {"status": "pending", "reason": "manifest_missing", "epoch": epoch}
    except _SourceError as exc:
        return {
            "status": "pending",
            "reason": f"manifest_{exc.reason}",
            "epoch": epoch,
        }
    if (
        manifest.get("schema_version") != PROJECTION_SCHEMA_VERSION
        or manifest.get("projection_kind") != "manifest"
        or manifest.get("epoch") != epoch
    ):
        return {
            "status": "pending",
            "reason": "manifest_incompatible",
            "epoch": epoch,
        }
    if not _validate_epoch_pages(base, epoch, manifest):
        return {"status": "pending", "reason": "page_invalid", "epoch": epoch}
    return manifest


def publish_audit_projection(
    root: Path,
    pass_result: object,
    prior_epoch: str | None = None,
    *,
    interval_seconds: int,
    observed_at: datetime | None = None,
    max_page_rows: int = MAX_PAGE_ROWS,
    max_page_bytes: int = MAX_PAGE_BYTES,
) -> str:
    """Publish complete immutable pages before atomically switching the pointer."""

    if type(interval_seconds) is not int or interval_seconds <= 0:
        raise ValueError("projection interval must be positive")
    if not 1 <= max_page_rows <= MAX_PAGE_ROWS or max_page_bytes < 1024:
        raise ValueError("invalid projection page bounds")
    now = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fresh_until = (now + timedelta(seconds=2 * interval_seconds + 60)).isoformat()
    base = projection_root(root)
    prior_manifest = read_projection_manifest(root)
    if prior_epoch is not None and prior_manifest.get("epoch") != prior_epoch:
        prior_manifest = {"status": "pending", "reason": "prior_epoch_mismatch"}
    prior_rows = _read_prior_rows(base, prior_manifest)
    source_revisions, source_failures = _source_markers(root)
    sources = project_recovery_sources(root)
    current, coverage, history = _reconcile_projection(
        prior_rows,
        sources,
        tuple(getattr(pass_result, "projection_observations", ())),
        tuple(getattr(pass_result, "candidate_failures", ())),
        now,
        fresh_until,
        (now + timedelta(seconds=interval_seconds)).isoformat(),
        coverage_deferred=bool(getattr(pass_result, "coverage_deferred", False)),
    )
    rows = {
        "current": [item.as_dict() for item in current],
        "coverage": [item.as_dict() for item in coverage],
        "history": [item.as_dict() for item in history],
    }
    epoch = f"epoch-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:12]}"
    pages = {
        name: _bounded_pages(name, values, epoch, max_page_rows, max_page_bytes)
        for name, values in rows.items()
    }
    if (source_revisions, source_failures) != _source_markers(root):
        raise RuntimeError("projection recovery source changed during publication")
    if (
        isinstance(prior_manifest.get("epoch"), str)
        and prior_rows == rows
        and _manifest_has_aggregates(prior_manifest)
        and _manifest_source_markers(prior_manifest)
        == (source_revisions, source_failures)
    ):
        # Preserve receipt-only silence when a completed healthy pass has no
        # material current, coverage, history, or source-marker change.
        return str(prior_manifest["epoch"])
    product_identity, tracking_identity = _repository_identities(root)
    manifest = ProjectionManifest(
        epoch=epoch,
        observed_at=now.isoformat(),
        interval_seconds=interval_seconds,
        fresh_until=fresh_until,
        product_identity=product_identity,
        tracking_identity=tracking_identity,
        page_counts={name: len(value) for name, value in pages.items()},
        row_counts={name: len(value) for name, value in rows.items()},
        **_coverage_aggregates(rows["coverage"]),
        source_revisions=source_revisions,
        source_failures=source_failures,
    ).as_dict()

    base.mkdir(parents=True, exist_ok=True)
    epoch_dir = base / epoch
    epoch_dir.mkdir()
    try:
        for section, section_pages in pages.items():
            section_dir = epoch_dir / section
            section_dir.mkdir()
            for index, page in enumerate(section_pages):
                _write_json_durable(section_dir / f"{index:06d}.json", page)
            _fsync_directory(section_dir)
        _write_json_durable(epoch_dir / "manifest.json", manifest)
        _fsync_directory(epoch_dir)
        _write_json_atomically(
            base / "current.json",
            {"schema_version": PROJECTION_SCHEMA_VERSION, "epoch": epoch},
        )
        _fsync_directory(base)
    except Exception:
        # Retain an unreferenced partial directory as interruption evidence.
        raise
    return epoch


def _repository_identities(root: Path) -> tuple[str, str]:
    from cascade.board.context import get_project_context, resolve_tracking_root

    product = canonical_audit_root(root)
    project = get_project_context()
    if project is not None and product == project.target.root:
        return str(project.target.repository_key), str(project.tracking.repository_key)
    tracking = resolve_tracking_root(product)
    return (
        "repository-" + hashlib.sha256(product.as_uri().encode()).hexdigest()[:24],
        "repository-" + hashlib.sha256(tracking.as_uri().encode()).hexdigest()[:24],
    )


def projection_repository_identities(root: Path) -> tuple[str, str]:
    """Return the product/tracking keys a consumer must find in a manifest."""

    return _repository_identities(root)


def _coverage_aggregates(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    statuses: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in rows:
        status = str(row["verification_status"])
        reason = str(row["reason"])
        statuses[status] = statuses.get(status, 0) + 1
        reasons[reason] = reasons.get(reason, 0) + 1
    ordered = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    retained = dict(ordered[:MAX_AGGREGATE_REASONS])
    return {
        "coverage_by_status": statuses,
        "coverage_by_reason": retained,
        "coverage_other_reasons": sum(
            count for _reason, count in ordered[MAX_AGGREGATE_REASONS:]
        ),
    }


def _source_markers(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    home = canonical_audit_root(root) / ".cascade"
    revisions: dict[str, str] = {}
    failures: dict[str, str] = {}
    for store, filename, _collection in _STORE_SPECS:
        try:
            descriptor = os.open(
                home / filename,
                os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
            )
        except FileNotFoundError:
            failures[store] = "source_missing"
            continue
        except OSError:
            failures[store] = "source_unreadable"
            continue
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                failures[store] = "source_not_regular"
                continue
            if info.st_size > MAX_SOURCE_BYTES:
                failures[store] = "source_too_large"
                continue
            content = os.read(descriptor, MAX_SOURCE_BYTES + 1)
            if len(content) > MAX_SOURCE_BYTES:
                failures[store] = "source_too_large"
                continue
            revisions[store] = "sha256:" + hashlib.sha256(content).hexdigest()
        finally:
            os.close(descriptor)
    return revisions, failures


def _read_prior_rows(
    base: Path, manifest: Mapping[str, object]
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {
        "current": [],
        "coverage": [],
        "history": [],
    }
    epoch = manifest.get("epoch")
    sections = manifest.get("sections")
    if not isinstance(epoch, str) or not isinstance(sections, Mapping):
        return result
    for name in result:
        section = sections.get(name)
        count = section.get("page_count") if isinstance(section, Mapping) else None
        if type(count) is not int or not 0 <= count <= 100000:
            return {"current": [], "coverage": [], "history": []}
        try:
            for index in range(count):
                page = _read_json_object(
                    base / epoch / name / f"{index:06d}.json", MAX_PAGE_BYTES
                )
                if page.get("epoch") != epoch or page.get("projection_kind") != name:
                    raise _SourceError("page_incompatible")
                page_rows = page.get("rows")
                if not isinstance(page_rows, list) or len(page_rows) > MAX_PAGE_ROWS:
                    raise _SourceError("page_incompatible")
                result[name].extend(row for row in page_rows if isinstance(row, dict))
        except (FileNotFoundError, _SourceError):
            return {"current": [], "coverage": [], "history": []}
    return result


def _validate_epoch_pages(
    base: Path, epoch: str, manifest: Mapping[str, object]
) -> bool:
    sections = manifest.get("sections")
    if not isinstance(sections, Mapping):
        return False
    for name in ("current", "coverage", "history"):
        section = sections.get(name)
        count = section.get("page_count") if isinstance(section, Mapping) else None
        if type(count) is not int or not 0 <= count <= 100000:
            return False
        for index in range(count):
            try:
                page = _read_json_object(
                    base / epoch / name / f"{index:06d}.json", MAX_PAGE_BYTES
                )
            except (FileNotFoundError, _SourceError):
                return False
            rows = page.get("rows")
            if (
                page.get("schema_version") != PROJECTION_SCHEMA_VERSION
                or page.get("projection_kind") != name
                or page.get("epoch") != epoch
                or not isinstance(rows, list)
                or not 1 <= len(rows) <= MAX_PAGE_ROWS
                or any(not isinstance(row, dict) for row in rows)
            ):
                return False
    return True


def _manifest_source_markers(
    manifest: Mapping[str, object],
) -> tuple[dict[str, str], dict[str, str]]:
    revisions: dict[str, str] = {}
    failures: dict[str, str] = {}
    sources = manifest.get("sources")
    if not isinstance(sources, Mapping):
        return revisions, failures
    for store, value in sources.items():
        if store not in _STORE_NAMES or not isinstance(value, Mapping):
            continue
        revision = value.get("revision")
        failure = value.get("failure")
        if isinstance(revision, str):
            revisions[store] = revision
        if isinstance(failure, str):
            failures[store] = failure
    return revisions, failures


def _manifest_has_aggregates(manifest: Mapping[str, object]) -> bool:
    sections = manifest.get("sections")
    return (
        isinstance(sections, Mapping)
        and all(
            isinstance(sections.get(name), Mapping)
            and type(sections[name].get("row_count")) is int
            for name in ("current", "coverage", "history")
        )
        and isinstance(manifest.get("coverage_aggregates"), Mapping)
    )


def _reconcile_projection(
    prior: Mapping[str, list[dict[str, object]]],
    sources: RecoveryProjection,
    observations: Sequence[Mapping[str, object]],
    failures: Sequence[Mapping[str, object]],
    now: datetime,
    fresh_until: str,
    next_attempt_at: str,
    *,
    coverage_deferred: bool,
) -> tuple[
    tuple[CurrentSummary, ...],
    tuple[CoverageSummary, ...],
    tuple[HistorySummary, ...],
]:
    observed_by_work = {
        str(item.get("work_id")): item
        for item in observations
        if isinstance(item.get("work_id"), str)
    }
    current: list[CurrentSummary] = []
    coverage: list[CoverageSummary] = list(sources.coverage)
    history: list[HistorySummary] = list(sources.history)

    for raw in prior.get("current", []):
        if raw.get("work_id") in observed_by_work:
            continue
        try:
            expiry = datetime.fromisoformat(str(raw.get("fresh_until")))
            item = _summary_from_dict(raw, CurrentSummary)
        except (TypeError, ValueError):
            continue
        if expiry > now:
            current.append(item)
        else:
            coverage.append(_stale_coverage(item))

    source_current = {
        (item.work_id, item.authoritative_generation, item.failure_class): item
        for item in sources.current
    }
    stale_coverage_keys = {
        _coverage_key(item)
        for item in _safe_prior_summaries(prior.get("coverage", []), CoverageSummary)
        if item.verification_status == "stale"
    } | {
        _coverage_key(item) for item in coverage if item.verification_status == "stale"
    }
    matched_source_keys: set[tuple[str | None, str | None, str | None]] = set()
    for work_id, observation in observed_by_work.items():
        classification = observation.get("classification")
        generation = observation.get("authoritative_generation")
        failure_class = observation.get("failure_class")
        verified = now.isoformat()
        match = source_current.get((work_id, generation, failure_class))
        if classification == "proven_incident" and match is not None:
            matched_source_keys.add((work_id, generation, failure_class))
            values = {
                name: getattr(match, name) for name in AuditSummary.__dataclass_fields__
            }
            values.update(last_verified_at=verified, fresh_until=fresh_until)
            current.append(CurrentSummary(**values))
        else:
            coverage.append(
                CoverageSummary(
                    None,
                    work_id,
                    _text(observation.get("owner")),
                    _generation(generation),
                    _text(failure_class),
                    None,
                    verified,
                    verified,
                    "verified" if classification == "healthy" else "pending",
                    _bounded_reason(
                        observation.get("reason") or classification or "unknown"
                    ),
                    fresh_until,
                    next_attempt_at if classification != "healthy" else None,
                )
            )
    for key, item in source_current.items():
        if key in matched_source_keys:
            continue
        pending_key = _coverage_key(item)
        if pending_key in stale_coverage_keys:
            continue
        values = {
            name: getattr(item, name) for name in AuditSummary.__dataclass_fields__
        }
        values.update(
            verification_status="pending",
            reason="authoritative_reassessment_pending",
            next_attempt_at=next_attempt_at,
        )
        coverage.append(CoverageSummary(**values))
    for failure in failures:
        coverage.append(
            CoverageSummary(
                None,
                _text(failure.get("work_id")),
                None,
                None,
                None,
                None,
                now.isoformat(),
                None,
                "pending",
                _bounded_reason(failure.get("reason") or "audit_observation_error"),
                next_attempt_at=next_attempt_at,
            )
        )
    if coverage_deferred:
        coverage.append(
            CoverageSummary(
                None,
                None,
                None,
                None,
                None,
                None,
                now.isoformat(),
                None,
                "pending",
                "deferred_by_budget",
            )
        )

    new_coverage_keys = {_coverage_key(item) for item in coverage}
    coverage.extend(
        item
        for item in _safe_prior_summaries(prior.get("coverage", []), CoverageSummary)
        if item.work_id not in observed_by_work
        and _coverage_key(item) not in new_coverage_keys
    )
    history.extend(_safe_prior_summaries(prior.get("history", []), HistorySummary))
    current = _dedupe_summaries(current)
    coverage = _dedupe_summaries(coverage)
    history = _dedupe_summaries(history)
    current.sort(key=lambda item: (item.work_id or "", _ref_key(item.source_ref)))
    coverage.sort(
        key=lambda item: (item.work_id or "", _ref_key(item.source_ref), item.reason)
    )
    history.sort(key=lambda item: (_ref_key(item.source_ref), item.occurred_at or ""))
    return tuple(current), tuple(coverage), tuple(history)


def _summary_from_dict(
    raw: Mapping[str, object], cls: type[AuditSummary]
) -> AuditSummary:
    ref_raw = raw.get("source_ref")
    ref = None
    if isinstance(ref_raw, Mapping):
        ref = SourceRef(
            ref_raw.get("store"),  # type: ignore[arg-type]
            ref_raw.get("row_key"),  # type: ignore[arg-type]
            ref_raw.get("incident_history_ordinal"),  # type: ignore[arg-type]
        )
    values = {name: raw.get(name) for name in AuditSummary.__dataclass_fields__}
    values["source_ref"] = ref
    values["provenance"] = raw.get("provenance") or {}
    return cls(**values)


def _safe_prior_summaries(
    raw_rows: Sequence[Mapping[str, object]], cls: type[AuditSummary]
) -> list[Any]:
    result = []
    for raw in raw_rows:
        try:
            result.append(_summary_from_dict(raw, cls))
        except (TypeError, ValueError):
            continue
    return result


def _stale_coverage(item: CurrentSummary) -> CoverageSummary:
    values = {name: getattr(item, name) for name in AuditSummary.__dataclass_fields__}
    values.update(verification_status="stale", reason="verification_stale")
    return CoverageSummary(**values)


def _dedupe_summaries(items: Sequence[Any]) -> list[Any]:
    unique = {}
    for item in items:
        key = json.dumps(item.as_dict(), sort_keys=True, separators=(",", ":"))
        unique[key] = item
    return list(unique.values())


def _coverage_key(item: AuditSummary) -> tuple[object, ...]:
    return (
        _ref_key(item.source_ref),
        item.work_id,
        tuple(sorted(item.provenance.items())),
    )


def _bounded_pages(
    kind: str,
    rows: Sequence[dict[str, object]],
    epoch: str,
    row_limit: int,
    byte_limit: int,
) -> list[dict[str, object]]:
    pages: list[dict[str, object]] = []
    pending: list[dict[str, object]] = []
    for row in rows:
        candidate = pending + [row]
        wrapper = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_kind": kind,
            "epoch": epoch,
            "rows": candidate,
        }
        if pending and (
            len(candidate) > row_limit or len(_json_bytes(wrapper)) > byte_limit
        ):
            pages.append(
                {
                    "schema_version": PROJECTION_SCHEMA_VERSION,
                    "projection_kind": kind,
                    "epoch": epoch,
                    "rows": pending,
                }
            )
            pending = [row]
        else:
            pending = candidate
        check = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_kind": kind,
            "epoch": epoch,
            "rows": pending,
        }
        if len(_json_bytes(check)) > byte_limit:
            raise ValueError("bounded projection row exceeds page byte ceiling")
    if pending:
        pages.append(
            {
                "schema_version": PROJECTION_SCHEMA_VERSION,
                "projection_kind": kind,
                "epoch": epoch,
                "rows": pending,
            }
        )
    return pages


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_json_durable(path: Path, value: Mapping[str, object]) -> None:
    with path.open("xb") as handle:
        handle.write(_json_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())


def _write_json_atomically(path: Path, value: Mapping[str, object]) -> None:
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
    request = incident.get("request")
    if isinstance(request, Mapping) and (
        stamp := _timestamp(request.get("delivered_at"))
    ):
        attempted.append(stamp)
    # A successful recovery attempt is not a fresh verification of the work
    # obligation.  Reconciliation supplies that timestamp after checking
    # canonical state for the matching generation.
    return occurred, max(attempted, default=None), None


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
            for name in (
                "observed_at",
                "occurred_at",
                "time",
                "created_at",
                "updated_at",
            )
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
                    "coverage_aggregates": {"type": "object"},
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
                    "coverage_aggregates",
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
    "MAX_PAGE_ROWS",
    "MAX_PAGE_BYTES",
    "MAX_MANIFEST_BYTES",
    "MAX_AGGREGATE_REASONS",
    "SourceRef",
    "AuditSummary",
    "CurrentSummary",
    "CoverageSummary",
    "HistorySummary",
    "ProjectionManifest",
    "RecoveryProjection",
    "projection_root",
    "projection_repository_identities",
    "read_projection_manifest",
    "publish_audit_projection",
    "project_recovery_sources",
    "projection_json_schema",
]
