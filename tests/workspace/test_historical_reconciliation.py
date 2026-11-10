"""Coverage accounting for pinned replay rows and accepted deltas."""

from dataclasses import replace

import pytest

from cascade.workspace import (
    BaselinePair,
    ExactRevisionReference,
    HistoricalEvidenceInventory,
    MaterialGap,
    ReplayDisposition,
    WorkspaceError,
    build_acceptance_summary,
    reconcile_replay_coverage,
)


REVISION = "a" * 40
DIRECT = "b" * 40
MERGE = "c" * 40
PLAN = "d" * 40


def _inventory() -> HistoricalEvidenceInventory:
    return HistoricalEvidenceInventory(
        owner_work_id="feat_001",
        target_repository_key="target-key",
        target_baseline=REVISION,
        tracking_baseline=REVISION,
        work_items=({"work_id": "task_001", "review_ids": []},),
        commits=({"commit_id": DIRECT, "review_ids": ["7"]},),
        reviews=({"review_id": "7", "forge": "github"},),
        ledger=(
            {"row_id": "work:task_001"},
            {"row_id": f"commit:{DIRECT}"},
        ),
        unavailable=(),
        baseline_pair=BaselinePair(
            target_repository_key="target-key",
            target_revision=REVISION,
            tracking_repository_key="target-key",
            tracking_revision=REVISION,
            g_artifact_repository_key="target-key",
            g_artifact_repository_role="target",
            g_artifact_path="architecture/inventory.json",
            g_artifact_revision=REVISION,
            g_artifact_sha256="0" * 64,
            integrations=({
                "work_id": "feat_001",
                "review_id": "7",
                "merge_revision": MERGE,
            },),
            accepted_deltas=({"revision": PLAN, "kind": "plan_update"},),
        ),
    )


def _reference(path: str = "cascade/service.py") -> ExactRevisionReference:
    return ExactRevisionReference(REVISION, path, "current behavior checked")


def _dispositions() -> list[ReplayDisposition]:
    return [
        ReplayDisposition(
            "work:task_001",
            "unresolved",
            "work:task_001 lacks its authorized child provenance",
            ("work:task_001",),
            (_reference("DESIGN.md"),),
            (_reference("tests/test_service.py"),),
            ("REQ-ROOT-001",),
            ("DEC-ROOT-001",),
            (),
            material_gap=MaterialGap(
                True, "child_record_unavailable", "feat_001", "owner handoff"
            ),
        ),
        ReplayDisposition(
            f"commit:{DIRECT}",
            "durable",
            f"commit:{DIRECT} is a directly verified non-review fix",
            (f"commit:{DIRECT}", "review:github:7"),
            (_reference(),),
            (_reference("tests/test_service.py"),),
            ("REQ-ROOT-001",),
            ("DEC-ROOT-001",),
            (),
            ("7",),
        ),
        ReplayDisposition(
            f"delta:{MERGE}",
            "durable",
            f"delta:{MERGE} is the accepted MR-described integration",
            (f"delta:{MERGE}", "review:7"),
            (_reference(),),
            (_reference("tests/test_service.py"),),
            ("REQ-ROOT-001",),
            ("DEC-ROOT-001",),
            (),
            ("7",),
        ),
        ReplayDisposition(
            f"delta:{PLAN}",
            "no-impact",
            f"delta:{PLAN} changes only its pinned plan metadata",
            (f"delta:{PLAN}",),
            (_reference("docs/epics/plan.md"),),
            (),
            ("REQ-ROOT-001",),
            ("DEC-ROOT-001",),
            (),
        ),
    ]


def test_reconciliation_balances_original_delta_and_overlapping_evidence() -> None:
    ledger = {"rows": list(_inventory().ledger), "inventory_sha256": "hash"}

    result = reconcile_replay_coverage(_inventory(), ledger, _dispositions())

    assert result["coverage_accounting"] == {
        "original_expected": 2,
        "original_covered": 2,
        "accepted_delta_expected": 2,
        "accepted_delta_covered": 2,
        "total_expected": 4,
        "total_covered": 4,
        "duplicate_rows": 0,
        "missing_rows": 0,
        "dispositions": {
            "durable": 2,
            "no-impact": 1,
            "superseded": 0,
            "unresolved": 1,
        },
        "material_unresolved": 1,
    }
    rows = {row["row_id"]: row for row in result["rows"]}
    assert "review:github:7" in rows[f"commit:{DIRECT}"]["evidence_keys"]
    assert "review:7" in rows[f"delta:{MERGE}"]["evidence_keys"]
    assert rows["work:task_001"]["material_gap"]["material"] is True


@pytest.mark.parametrize("failure", ("missing", "unsupported", "blanket"))
def test_reconciliation_rejects_unaccountable_claims(failure: str) -> None:
    rows = _dispositions()
    if failure == "missing":
        rows.pop()
    elif failure == "unsupported":
        rows[1] = replace(rows[1], evidence_keys=(rows[1].row_id, "commit:" + "f" * 40))
    else:
        rationale = f"delta:{MERGE} delta:{PLAN} blanket no-impact"
        rows[2] = replace(rows[2], disposition="no-impact", rationale=rationale)
        rows[3] = replace(rows[3], rationale=rationale)

    with pytest.raises(WorkspaceError):
        reconcile_replay_coverage(
            _inventory(), {"rows": list(_inventory().ledger)}, rows
        )


def _acceptance_inputs() -> dict[str, object]:
    return {
        "owner_work_id": "task_034_008_003",
        "baseline_pair": {
            "target_revision": REVISION,
            "tracking_revision": REVISION,
        },
        "expected_target_revision": REVISION,
        "expected_tracking_revision": REVISION,
        "artifacts": ({"name": "ledger", "revision": REVISION, "sha256": "0" * 64},),
        "required_artifacts": ("ledger",),
        "expected_artifacts": {
            "ledger": {"revision": REVISION, "sha256": "0" * 64},
        },
        "architecture_reviews": ({
            "review_unit_id": "architecture-review-1",
            "artifact_revision": REVISION,
            "accepted_revision_id": "accepted-1",
            "status": "accepted",
            "owner": "feature_architect",
        },),
        "receipt_validations": tuple({
            "tier": tier,
            "work_id": work_id,
            "status": "passed",
            "code": "ok",
            "receipt_id": f"receipt-{tier}",
            "owner": owner,
        } for tier, work_id, owner in (
            ("task", "task_034_008_003", "feature_team"),
            ("feature", "feat_034_008", "feature_team"),
            ("epic", "epic_034", "epic_team"),
        )),
        "coverage_accounting": {"material_unresolved": 0},
        "accepted_deltas": ({"revision": MERGE, "disposition": "no-impact"},),
    }


def test_acceptance_summary_is_clean_only_with_exact_accepted_evidence() -> None:
    summary = build_acceptance_summary(**_acceptance_inputs())

    assert summary["clean_closeout"] is True
    assert summary["blockers"] == []
    assert summary["architecture_reviews"][0]["accepted_revision_id"] == "accepted-1"
    assert {row["tier"] for row in summary["receipt_validations"]} == {
        "task", "feature", "epic"
    }


@pytest.mark.parametrize(
    ("change", "outcome"),
    (
        ("stale_baseline", "stale_baseline"),
        ("stale_artifact", "stale_baseline"),
        ("pending_review", "acceptance_pending"),
        ("missing_receipt", "missing_evidence"),
        ("material_rows", "material_mismatch"),
    ),
)
def test_acceptance_summary_rejects_incomplete_closeout(change: str, outcome: str) -> None:
    values = _acceptance_inputs()
    if change == "stale_baseline":
        values["expected_target_revision"] = DIRECT
    elif change == "stale_artifact":
        values["expected_artifacts"] = {
            "ledger": {"revision": DIRECT, "sha256": "0" * 64},
        }
    elif change == "pending_review":
        values["architecture_reviews"] = ({
            **values["architecture_reviews"][0],
            "status": "staged",
            "accepted_revision_id": None,
        },)
    elif change == "missing_receipt":
        values["receipt_validations"] = values["receipt_validations"][:-1]
    else:
        values["coverage_accounting"] = {"material_unresolved": 7}

    summary = build_acceptance_summary(**values)

    assert summary["clean_closeout"] is False
    assert outcome in {row["outcome"] for row in summary["blockers"]}
    assert all(row["owner"] and row["prerequisite"] for row in summary["blockers"])
