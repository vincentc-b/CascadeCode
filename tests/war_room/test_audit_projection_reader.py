import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.war_room.audit_projection_reader import (
    MAX_REQUEST_READ_BYTES,
    MAX_RESPONSE_BYTES,
    AuditPageRequest,
    AuditProjectionRequestError,
    read_audit_projection,
    read_audit_snapshot_header,
)
from cascade.watchdog.audit_projection import (
    HistorySummary,
    ProjectionManifest,
    SourceRef,
    projection_repository_identities,
    projection_root,
)


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _row(index: int, *, owner: str = "feature:feat_001") -> dict[str, object]:
    return HistorySummary(
        SourceRef("action_recovery", f"attempt-{index}"),
        f"task_{index:05d}",
        owner,
        None,
        "delivery_stalled",
        (NOW - timedelta(seconds=index)).isoformat(),
        NOW.isoformat(),
        None,
        "unverifiable",
        "historical_attempt",
        detail_truncated=index % 2 == 0,
        provenance={"legacy": str(index)},
    ).as_dict()


def _publish(
    root: Path,
    sections: dict[str, list[dict[str, object]]],
    *,
    epoch: str = "epoch-one",
    product: str | None = None,
    tracking: str | None = None,
) -> None:
    base = projection_root(root)
    product_key, tracking_key = projection_repository_identities(root)
    pages: dict[str, list[list[dict[str, object]]]] = {}
    for name in ("current", "coverage", "history"):
        rows = sections.get(name, [])
        pages[name] = [rows[index : index + 100] for index in range(0, len(rows), 100)]
    coverage = sections.get("coverage", [])
    statuses: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in coverage:
        status = str(row["verification_status"])
        reason = str(row["reason"])
        statuses[status] = statuses.get(status, 0) + 1
        reasons[reason] = reasons.get(reason, 0) + 1
    manifest = ProjectionManifest(
        epoch=epoch,
        observed_at=NOW.isoformat(),
        interval_seconds=60,
        fresh_until=(NOW + timedelta(minutes=3)).isoformat(),
        product_identity=product or product_key,
        tracking_identity=tracking or tracking_key,
        page_counts={name: len(pages[name]) for name in pages},
        row_counts={name: len(sections.get(name, [])) for name in pages},
        coverage_by_status=statuses,
        coverage_by_reason=reasons,
    ).as_dict()
    for name, section_pages in pages.items():
        for index, rows in enumerate(section_pages):
            _write(
                base / epoch / name / f"{index:06d}.json",
                {
                    "schema_version": 2,
                    "projection_kind": name,
                    "epoch": epoch,
                    "rows": rows,
                },
            )
    _write(base / epoch / "manifest.json", manifest)
    _write(base / "current.json", {"schema_version": 2, "epoch": epoch})


def test_reader_filters_across_pages_and_preserves_bounded_provenance(tmp_path: Path) -> None:
    rows = [_row(index, owner="wanted" if index in {150, 205} else "other") for index in range(230)]
    _publish(tmp_path, {"history": rows})

    first = read_audit_projection(
        tmp_path,
        AuditPageRequest("history", limit=1, owner="wanted"),
        now=NOW,
    )

    assert first["state"] == "ready"
    page = first["page"]
    assert page["returned"] == 1
    assert page["scanned"] == 151
    assert page["complete"] is False
    assert page["rows"][0]["source_ref"]["row_key"] == "attempt-150"
    assert page["rows"][0]["detail_truncated"] is True
    assert page["rows"][0]["provenance"] == {"legacy": "150"}

    second = read_audit_projection(
        tmp_path,
        AuditPageRequest("history", cursor=page["next_cursor"], limit=1, owner="wanted"),
        now=NOW,
    )
    assert second["page"]["rows"][0]["work_id"] == "task_00205"


def test_header_rejects_stale_wrong_root_and_invalid_aggregate(tmp_path: Path) -> None:
    _publish(tmp_path, {"history": [_row(1)]}, product="wrong-product")
    assert read_audit_snapshot_header(tmp_path, now=NOW)["reason"] == "repository_identity_mismatch"

    product, tracking = projection_repository_identities(tmp_path)
    _publish(tmp_path, {"history": [_row(1)]}, product=product, tracking=tracking)
    assert read_audit_snapshot_header(tmp_path, now=NOW + timedelta(minutes=4))["reason"] == "snapshot_stale"

    manifest_path = projection_root(tmp_path) / "epoch-one" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["coverage_aggregates"]["other_reasons"] = 1
    _write(manifest_path, manifest)
    assert read_audit_snapshot_header(tmp_path, now=NOW)["reason"] == "manifest_incompatible"


def test_reader_rejects_corrupt_page_symlink_and_mismatched_cursor(tmp_path: Path) -> None:
    _publish(tmp_path, {"history": [_row(1), _row(2)]})
    first = read_audit_projection(tmp_path, AuditPageRequest("history", limit=1), now=NOW)
    cursor = first["page"]["next_cursor"]
    with pytest.raises(AuditProjectionRequestError, match="does not match"):
        read_audit_projection(
            tmp_path,
            AuditPageRequest("history", cursor=cursor, limit=1, owner="different"),
            now=NOW,
        )
    with pytest.raises(AuditProjectionRequestError, match="malformed"):
        read_audit_projection(
            tmp_path / "missing",
            AuditPageRequest("history", cursor="../page"),
            now=NOW,
        )

    page_path = projection_root(tmp_path) / "epoch-one" / "history" / "000000.json"
    page_path.unlink()
    assert read_audit_projection(tmp_path, AuditPageRequest("history"), now=NOW)["reason"] == "page_missing"
    page_path.symlink_to(projection_root(tmp_path) / "current.json")
    assert read_audit_projection(tmp_path, AuditPageRequest("history"), now=NOW)["reason"] == "page_unreadable"


def test_old_cursor_requires_restart_after_new_epoch(tmp_path: Path) -> None:
    _publish(tmp_path, {"history": [_row(1), _row(2)]})
    first = read_audit_projection(tmp_path, AuditPageRequest("history", limit=1), now=NOW)
    _publish(tmp_path, {"history": [_row(3)]}, epoch="epoch-two")

    changed = read_audit_projection(
        tmp_path,
        AuditPageRequest("history", limit=1, cursor=first["page"]["next_cursor"]),
        now=NOW,
    )
    assert changed == {
        "state": "pending",
        "reason": "epoch_changed",
        "restart": True,
        "epoch": "epoch-two",
        "previous_epoch": "epoch-one",
        "last_observed_at": NOW.isoformat(),
    }


def test_ten_thousand_attempts_stop_at_read_and_response_ceilings(tmp_path: Path) -> None:
    _publish(tmp_path, {"history": [_row(index) for index in range(10_000)]})
    result = read_audit_projection(
        tmp_path,
        AuditPageRequest("history", limit=100, owner="does-not-match"),
        now=NOW,
    )

    assert result["state"] == "ready"
    assert result["page"]["complete"] is False
    assert result["page"]["reason"] == "read_budget"
    assert result["page"]["read_bytes"] <= MAX_REQUEST_READ_BYTES
    assert len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) <= MAX_RESPONSE_BYTES
    assert result["page"]["next_cursor"]
