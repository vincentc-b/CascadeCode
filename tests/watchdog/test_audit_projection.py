import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.watchdog.audit_projection import (
    PROJECTION_SCHEMA_VERSION,
    CurrentSummary,
    ProjectionManifest,
    SourceRef,
    publish_audit_projection,
    project_recovery_sources,
    projection_json_schema,
    projection_root,
    read_projection_manifest,
)
from cascade.watchdog.audit_lane import AuditPassResult


STAMP = "2026-11-14T12:00:00+00:00"
GENERATION = "sha256:" + "a" * 64
PRIOR_GENERATION = "sha256:" + "b" * 64


def _incident(*, generation: str = GENERATION, outcome: str = "error") -> dict:
    return {
        "schema_version": 1,
        "work_id": "task_001",
        "work": {"work_id": "task_001", "tier": "task"},
        "accountable_owner": "feature:feat_001",
        "failure_class": "delivery_stalled",
        "authoritative_generation": generation,
        "selected_capability": "recover_delivery",
        "recorded_at": STAMP,
        "next_reassessment_at": "2026-11-14T12:01:00+00:00",
        "attempts": [
            {
                "attempt": 1,
                "started_at": "2026-11-14T11:58:00+00:00",
                "completed_at": "2026-11-14T11:59:00+00:00",
                "outcome": "succeeded",
            },
            {
                "attempt": 2,
                "started_at": STAMP,
                "outcome": "failed",
            },
        ],
        "outcome": outcome,
    }


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_models_reject_paths_and_ambiguous_current_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown recovery store"):
        SourceRef("../../credentials", "row")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="unambiguous work"):
        CurrentSummary(
            SourceRef("action_recovery", "row"),
            None,
            "feature:feat_001",
            GENERATION,
            "delivery_stalled",
            STAMP,
            STAMP,
            None,
            "proven_incident",
            "modern_incident_identity",
        )

    assert projection_root(tmp_path) == (
        tmp_path / ".cascade" / "health_audit" / "projections"
    )


def test_projects_all_stores_history_legacy_and_malformed_neighbors_without_writes(
    tmp_path: Path,
) -> None:
    home = tmp_path / ".cascade"
    modern = _incident()
    prior = _incident(generation=PRIOR_GENERATION, outcome="success")
    ambiguous = _incident()
    ambiguous["work"] = {"work_id": "task_002", "tier": "task"}
    _write(
        home / "executions.json",
        {
            "actions": {
                "action-1": {
                    "incident": modern,
                    "incident_history": [prior, "broken neighbor"],
                },
                "malformed": ["not", "a", "row"],
                "ambiguous": {"incident": ambiguous},
            }
        },
    )
    _write(
        home / "orphan_delivery_recoveries.json",
        {"recoveries": {"delivery-1": {"incident": _incident()}}},
    )
    _write(
        home / "remediation_dispositions.json",
        {
            "dispositions": {
                "legacy-1": {
                    "incident": {
                        "child_id": "task_legacy",
                        "observed_child_sha": "0123456789abcdef",
                        "supervisor_id": "feat_legacy",
                    },
                    "action": "retry_task",
                    "result": "refused",
                    "reason": "owner unavailable",
                    "observed_at": STAMP,
                }
            }
        },
    )
    before = {path: path.read_bytes() for path in home.iterdir()}

    projected = project_recovery_sources(tmp_path)

    assert {item.source_ref.store for item in projected.current} == {
        "action_recovery",
        "orphan_delivery",
    }
    action = next(
        item for item in projected.current if item.source_ref.store == "action_recovery"
    )
    assert action.source_ref.as_dict() == {
        "store": "action_recovery",
        "row_key": "action-1",
    }
    assert action.occurred_at == STAMP
    assert action.last_attempted_at == STAMP
    assert action.last_verified_at is None

    prior_row = next(
        item
        for item in projected.history
        if item.source_ref.incident_history_ordinal == 0
    )
    assert prior_row.authoritative_generation == PRIOR_GENERATION
    assert prior_row.verification_status == "unverifiable"
    assert prior_row.reason == "historical_attempt"
    assert prior_row.last_verified_at is None

    legacy = next(
        item
        for item in projected.history
        if item.reason == "legacy_identity_unverifiable"
    )
    assert legacy.authoritative_generation is None
    assert legacy.failure_class is None
    assert legacy.occurred_at == STAMP
    assert legacy.provenance == {
        "child_id": "task_legacy",
        "observed_child_sha": "0123456789abcdef",
        "supervisor_id": "feat_legacy",
        "action": "retry_task",
        "result": "refused",
        "reason": "owner unavailable",
    }
    assert {item.reason for item in projected.coverage} >= {
        "row_malformed",
        "incident_history_item_malformed",
        "modern_identity_incomplete",
    }
    assert {path: path.read_bytes() for path in home.iterdir()} == before


def test_large_details_are_referenced_not_copied_and_source_failures_are_coverage(
    tmp_path: Path,
) -> None:
    home = tmp_path / ".cascade"
    incident = _incident()
    incident["evidence"] = {
        "provider_prompt": "never publish me " * 200,
        "credential": "secret-token",
        "hidden_reasoning": "private chain",
    }
    _write(home / "executions.json", {"actions": {"large": {"incident": incident}}})
    _write(home / "orphan_delivery_recoveries.json", {"recoveries": {}})
    # The third source is deliberately absent: absence is not healthy coverage.

    projected = project_recovery_sources(tmp_path, max_detail_bytes=128)
    row = projected.current[0]
    serialized = json.dumps(row.as_dict())
    current_schema = projection_json_schema()["$defs"]["current"]
    assert current_schema["properties"]["source_ref"]["type"] == "object"
    assert row.detail_truncated is True
    assert "never publish me" not in serialized
    assert "secret-token" not in serialized
    assert "private chain" not in serialized
    assert any(
        item.reason == "source_missing"
        and item.provenance == {"store": "remediation_dispositions"}
        for item in projected.coverage
    )


def test_oversized_source_is_explicit_coverage(tmp_path: Path) -> None:
    home = tmp_path / ".cascade"
    _write(home / "executions.json", {"actions": {"row": {"padding": "x" * 100}}})

    projected = project_recovery_sources(tmp_path, max_source_bytes=32)

    assert any(
        item.reason == "source_too_large"
        and item.provenance == {"store": "action_recovery"}
        for item in projected.coverage
    )


def test_manifest_and_single_schema_cover_all_projection_artifacts() -> None:
    manifest = ProjectionManifest(
        epoch="epoch-001",
        observed_at=STAMP,
        interval_seconds=1800,
        fresh_until="2026-11-14T13:01:00+00:00",
        product_identity="product:/repo",
        tracking_identity="tracking:/repo",
        page_counts={"current": 1, "coverage": 1, "history": 2},
        source_revisions={"action_recovery": "sha256:source"},
        source_failures={"remediation_dispositions": "source_missing"},
    ).as_dict()
    schema = projection_json_schema()

    assert set(schema["$defs"]["manifest"]["required"]) <= set(manifest)
    assert manifest["schema_version"] == PROJECTION_SCHEMA_VERSION == 2
    assert manifest["projection_kind"] == "manifest"
    assert manifest["sections"] == {
        "current": {"page_count": 1},
        "coverage": {"page_count": 1},
        "history": {"page_count": 2},
    }
    assert schema["$id"].endswith("/v2")
    assert set(schema["$defs"]) == {"manifest", "current", "coverage", "history"}


def test_atomic_publisher_reconciles_matching_authority_and_bounds_pages(
    tmp_path: Path,
) -> None:
    home = tmp_path / ".cascade"
    legacy = {
        f"legacy-{index}": {
            "child_id": f"task_{index:03d}",
            "observed_child_sha": f"sha-{index}",
            "supervisor_id": "feat_001",
            "observed_at": STAMP,
        }
        for index in range(101)
    }
    _write(
        home / "executions.json",
        {"actions": {"current": {"incident": _incident()}, **legacy}},
    )
    _write(home / "orphan_delivery_recoveries.json", {"recoveries": {}})
    _write(home / "remediation_dispositions.json", {"dispositions": {}})
    observed = datetime.fromisoformat(STAMP)
    result = AuditPassResult(
        projection_observations=(
            {
                "work_id": "task_001",
                "owner": "feat_001",
                "authoritative_generation": GENERATION,
                "failure_class": "delivery_stalled",
                "classification": "proven_incident",
                "reason": "validated_delivery_missing",
            },
        )
    )

    epoch = publish_audit_projection(
        tmp_path, result, interval_seconds=1800, observed_at=observed
    )
    manifest = read_projection_manifest(tmp_path)

    assert manifest["epoch"] == epoch
    assert manifest["fresh_until"] == (observed + timedelta(seconds=3660)).isoformat()
    assert manifest["sections"]["history"]["page_count"] == 2
    pointer = json.loads((projection_root(tmp_path) / "current.json").read_text())
    assert pointer == {"schema_version": 2, "epoch": epoch}
    current_page = json.loads(
        (projection_root(tmp_path) / epoch / "current" / "000000.json").read_text()
    )
    assert current_page["epoch"] == epoch
    assert current_page["rows"][0]["last_verified_at"] == STAMP
    assert current_page["rows"][0]["fresh_until"] == manifest["fresh_until"]
    for page in (projection_root(tmp_path) / epoch / "history").iterdir():
        payload = json.loads(page.read_text())
        assert len(payload["rows"]) <= 100
        assert page.stat().st_size <= 256 * 1024


def test_interrupted_pointer_swap_leaves_prior_epoch_readable_and_partial_unreferenced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / ".cascade"
    for filename, collection in (
        ("executions.json", "actions"),
        ("orphan_delivery_recoveries.json", "recoveries"),
        ("remediation_dispositions.json", "dispositions"),
    ):
        _write(home / filename, {collection: {}})
    first = publish_audit_projection(
        tmp_path,
        AuditPassResult(),
        interval_seconds=60,
        observed_at=datetime(2026, 11, 14, tzinfo=timezone.utc),
    )
    real_replace = os.replace

    def interrupt(source, destination):
        if Path(destination).name == "current.json":
            raise OSError("simulated pointer interruption")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", interrupt)
    with pytest.raises(OSError, match="pointer interruption"):
        publish_audit_projection(
            tmp_path,
            AuditPassResult(coverage_deferred=True),
            interval_seconds=60,
            observed_at=datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc),
        )

    assert read_projection_manifest(tmp_path)["epoch"] == first
    epochs = [path for path in projection_root(tmp_path).iterdir() if path.is_dir()]
    assert len(epochs) == 2


def test_manifest_reader_rejects_missing_page_and_unchanged_pass_is_silent(
    tmp_path: Path,
) -> None:
    home = tmp_path / ".cascade"
    _write(home / "executions.json", {"actions": {}})
    _write(home / "orphan_delivery_recoveries.json", {"recoveries": {}})
    _write(home / "remediation_dispositions.json", {"dispositions": {}})
    observed = datetime.fromisoformat(STAMP)
    first = publish_audit_projection(
        tmp_path, AuditPassResult(), interval_seconds=60, observed_at=observed
    )
    second = publish_audit_projection(
        tmp_path,
        AuditPassResult(),
        interval_seconds=60,
        observed_at=observed + timedelta(seconds=60),
    )
    assert second == first
    assert (
        len([path for path in projection_root(tmp_path).iterdir() if path.is_dir()])
        == 1
    )

    manifest_path = projection_root(tmp_path) / first / "manifest.json"
    damaged = json.loads(manifest_path.read_text())
    damaged["sections"]["coverage"]["page_count"] = 1
    manifest_path.write_text(json.dumps(damaged))
    assert read_projection_manifest(tmp_path) == {
        "status": "pending",
        "reason": "page_invalid",
        "epoch": first,
    }


def test_restart_preserves_pending_coverage_and_stales_expired_incident(
    tmp_path: Path,
) -> None:
    home = tmp_path / ".cascade"
    _write(home / "executions.json", {"actions": {"one": {"incident": _incident()}}})
    _write(home / "orphan_delivery_recoveries.json", {"recoveries": {}})
    _write(home / "remediation_dispositions.json", {"dispositions": {}})
    observed = datetime.fromisoformat(STAMP)
    incident = AuditPassResult(
        projection_observations=(
            {
                "work_id": "task_001",
                "authoritative_generation": GENERATION,
                "failure_class": "delivery_stalled",
                "classification": "proven_incident",
                "reason": "stalled",
            },
        )
    )
    publish_audit_projection(
        tmp_path, incident, interval_seconds=60, observed_at=observed
    )
    second = publish_audit_projection(
        tmp_path,
        AuditPassResult(
            candidate_failures=({"work_id": "task_002", "reason": "work_deleted"},)
        ),
        interval_seconds=60,
        observed_at=observed + timedelta(seconds=181),
    )
    manifest = read_projection_manifest(tmp_path)
    assert manifest["epoch"] == second
    coverage_pages = projection_root(tmp_path) / second / "coverage"
    rows = [
        row
        for path in coverage_pages.iterdir()
        for row in json.loads(path.read_text())["rows"]
    ]
    assert any(
        row["work_id"] == "task_001"
        and row["reason"] == "verification_stale"
        and row["last_verified_at"] == STAMP
        for row in rows
    )
    deleted = next(row for row in rows if row["reason"] == "work_deleted")
    assert deleted["next_attempt_at"] == (observed + timedelta(seconds=241)).isoformat()
