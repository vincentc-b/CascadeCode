"""Read-only War Room projection of published health-audit state."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_OUTCOMES = ("healthy", "expected_wait", "proven_incident", "unavailable_evidence")
_TIERS = ("task", "feature", "epic")
_RECEIPT_FIELDS = (
    "last_completed_at",
    "next_scheduled_at",
    "interval_seconds",
    "duration_seconds",
    "counts",
    "next_cursor",
)
_FAILURE_FIELDS = (
    "failed_at",
    "code",
    "message",
    "next_action",
    "retry_seconds",
    "cursor",
    "work_ids",
    "pending_timeout_work_ids",
)


def health_audit_status(*, root: Path) -> dict[str, object]:
    """Return the first verified-current page plus compact runtime metadata.

    The projection is the sole incident authority on this path. Receipt and
    failure files contribute scheduling/diagnostic metadata only; no lifecycle
    observation or recovery-ledger scan is performed.
    """

    # Lazy import preserves audit_lane -> audit -> health -> War Room startup.
    from cascade.war_room.audit_projection_reader import (
        MAX_RESPONSE_BYTES,
        AuditPageRequest,
        read_audit_projection,
    )

    projection = read_audit_projection(root, AuditPageRequest("current"))
    receipt, failure, unavailable = _runtime_metadata(root)
    from cascade.watchdog.audit_investigation import read_follow_up_snapshot

    follow_ups = read_follow_up_snapshot(root=root)
    if follow_ups.get("state") != "available":
        unavailable = [
            *unavailable,
            {
                "source": "audit_investigation_follow_ups",
                "reason": str(follow_ups.get("reason") or "snapshot_unavailable"),
            },
        ]
    result: dict[str, object] = {
        "schema_version": 2,
        "snapshot": _snapshot_state(projection),
        "state": projection.get("state", "pending"),
        "receipt": receipt,
        "failure": failure,
        # Legacy client fields retained during the schema-2 rollout.
        "last_run": receipt.get("last_completed_at") if receipt else None,
        "next_due": receipt.get("next_scheduled_at") if receipt else None,
        "duration_seconds": receipt.get("duration_seconds") if receipt else None,
        "interval_seconds": receipt.get("interval_seconds") if receipt else None,
        "counts": _project_counts(receipt.get("counts") if receipt else None),
        "incidents": [],
        "unavailable_evidence": unavailable,
        "investigation_snapshot": {
            name: follow_ups[name]
            for name in ("state", "reason", "version", "published_at", "source", "truncated", "unavailable_count")
            if name in follow_ups
        },
        "investigations": follow_ups.get("rows", []),
        "agent_schedule": {},
    }
    if projection.get("state") != "ready":
        reason = str(projection.get("reason") or "snapshot_unavailable")
        result["unavailable_evidence"] = [
            *unavailable,
            {"source": "audit_snapshot", "reason": reason},
        ]
        for field in ("epoch", "last_observed_at", "fresh_until", "restart"):
            if field in projection:
                result[field] = projection[field]
        return result

    header = projection["header"]
    page = projection["page"]
    assert isinstance(header, dict) and isinstance(page, dict)
    rows = page.get("rows")
    current_rows = rows if isinstance(rows, list) else []
    result.update(
        {
            "epoch": header["epoch"],
            "observed_at": header["observed_at"],
            "fresh_until": header["fresh_until"],
            "interval_seconds": header["interval_seconds"],
            "current": page,
            "coverage": header["coverage_aggregates"],
            "sections": header["sections"],
            "incidents": [
                _legacy_incident(row)
                for row in current_rows
                if isinstance(row, Mapping)
            ],
        }
    )
    if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_RESPONSE_BYTES:
        # Legacy aliases can make an otherwise valid projection page too large
        # when source provenance approaches its own ceiling. Fail explicitly
        # instead of silently dropping verified incidents or exceeding HTTP's
        # response contract.
        for field in ("current", "coverage", "sections", "incidents"):
            result.pop(field, None)
        result["state"] = "pending"
        result["snapshot"] = {
            "state": "pending",
            "reason": "response_budget",
            "epoch": header["epoch"],
            "last_observed_at": header["observed_at"],
        }
        result["unavailable_evidence"] = [
            *unavailable,
            {"source": "audit_snapshot", "reason": "response_budget"},
        ]
    return result


def _runtime_metadata(
    root: Path,
) -> tuple[dict[str, object] | None, dict[str, object] | None, list[dict[str, str]]]:
    # Lazy import avoids the audit_lane -> audit -> health import cycle during
    # supervisor startup. Both readers use regular-file no-follow 64 KiB caps.
    from cascade.watchdog.audit_lane import read_audit_failure, read_audit_receipt

    unavailable: list[dict[str, str]] = []
    try:
        receipt_raw = read_audit_receipt(root)
    except OSError as exc:
        receipt_raw = None
        unavailable.append({"source": "audit_receipt", "reason": type(exc).__name__})
    try:
        failure_raw = read_audit_failure(root)
    except OSError as exc:
        failure_raw = None
        unavailable.append({"source": "audit_failure", "reason": type(exc).__name__})
    return (
        _bounded_fields(receipt_raw, _RECEIPT_FIELDS),
        _bounded_fields(failure_raw, _FAILURE_FIELDS),
        unavailable,
    )


def _bounded_fields(
    value: object, allowed: tuple[str, ...]
) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {name: value[name] for name in allowed if name in value}


def _snapshot_state(projection: Mapping[str, object]) -> dict[str, object]:
    if projection.get("state") == "ready":
        header = projection.get("header")
        assert isinstance(header, Mapping)
        return {
            "state": "ready",
            "epoch": header["epoch"],
            "observed_at": header["observed_at"],
            "fresh_until": header["fresh_until"],
        }
    return {
        name: projection[name]
        for name in (
            "state",
            "reason",
            "epoch",
            "last_observed_at",
            "fresh_until",
            "restart",
        )
        if name in projection
    }


def _legacy_incident(row: Mapping[str, object]) -> dict[str, object]:
    """Map summary fields consumed by the interim JavaScript renderer."""

    source = row.get("source_ref")
    source = source if isinstance(source, Mapping) else {}
    return {
        "incident_id": str(
            source.get("row_key") or row.get("work_id") or "unavailable"
        ),
        "store": source.get("store"),
        "work_id": row.get("work_id"),
        "tier": _tier(row.get("work_id")),
        "owner": row.get("owner"),
        "failure_class": row.get("failure_class"),
        "generation": row.get("authoritative_generation"),
        "evidence": {"available": False, "value": None},
        "request": {"state": "unavailable", "value": None},
        "acknowledgement": {"available": False, "value": None},
        "result": {"available": False, "value": None},
        "outcome": row.get("verification_status"),
        "retry": {
            "state": "pending" if row.get("next_attempt_at") else "unavailable",
            "cooldown_until": row.get("next_attempt_at"),
            "claim_expires_at": None,
            "next_reassessment_at": row.get("next_attempt_at"),
            "policy": {},
            "attempts": [],
        },
        "resume_action": {"operation": "unavailable", "owner": row.get("owner")},
        "recorded_at": row.get("occurred_at"),
        "source_ref": dict(source),
        "detail_truncated": bool(row.get("detail_truncated")),
        "reason": row.get("reason"),
    }


def _tier(work_id: object) -> str | None:
    if not isinstance(work_id, str):
        return None
    return {"task": "task", "feat": "feature", "epic": "epic"}.get(
        work_id.split("_", 1)[0]
    )


def _project_counts(raw: object) -> dict[str, object]:
    values = raw if isinstance(raw, Mapping) else {}
    by_outcome = {name: _nonnegative_int(values.get(name)) for name in _OUTCOMES}
    by_tier: dict[str, dict[str, int]] = defaultdict(dict)
    for tier in _TIERS:
        for outcome in _OUTCOMES:
            by_tier[tier][outcome] = _nonnegative_int(
                values.get(f"tier.{tier}.{outcome}")
            )
    return {"by_outcome": by_outcome, "by_tier": dict(by_tier)}


def _nonnegative_int(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


__all__ = ["health_audit_status"]
