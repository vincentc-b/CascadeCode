"""Pinned completed-work and target-history inventory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cascade.workspace.historical_inventory import (
    AuthorizedReviewHandoff,
    AuthorizedWorkHandoff,
    build_historical_inventory,
    pin_historical_inventory,
    read_historical_inventory,
)
from cascade.workspace.types import ProjectContext
from tests.support import add_doc


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _repository(tmp_path: Path) -> tuple[ProjectContext, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _commit(root, "seed")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001_001", title="Feature", tier="feature",
        status="active", parent="epic_001",
    )
    completed = add_doc(
        root, id="task_001_001_001", title="Completed", tier="task",
        status="completed", parent="feat_001_001",
    )
    add_doc(
        root, id="task_001_001_002", title="Cancelled", tier="task",
        status="cancelled", parent="feat_001_001",
    )
    implementation = root / "implementation.txt"
    implementation.write_text("direct fix\n", encoding="utf-8")
    direct = _commit(root, "fix: direct change for task_001_001_001")
    receipts = root / "architecture" / "reconciliation-receipts.json"
    receipts.parent.mkdir(parents=True)
    receipts.write_text(json.dumps({
        "version": 1,
        "receipts": {
            "task_001_001_001": [{"implementation_revisions": [direct]}],
        },
    }), encoding="utf-8")
    reviews = root / ".cascade" / "reviews.json"
    reviews.parent.mkdir(parents=True, exist_ok=True)
    reviews.write_text(json.dumps({
        "task_001_001_001": {
            "url": "https://github.example/acme/repo/pull/7",
            "number": "7",
            "forge": "github",
            "description": "Implements the direct fix.",
            "source_revision": direct,
        },
    }), encoding="utf-8")
    baseline = _commit(root, "record durable evidence")
    assert completed.sha is not None
    return ProjectContext.colocated(root), baseline, direct


def test_inventory_pins_completed_work_and_deduplicates_covered_commits(
    tmp_path: Path,
) -> None:
    project, baseline, direct = _repository(tmp_path)

    inventory = build_historical_inventory(
        project, "feat_034_007", target_revision=baseline,
        tracking_revision=baseline,
    )

    assert inventory.target_baseline == baseline
    assert inventory.tracking_baseline == baseline
    assert [row["work_id"] for row in inventory.work_items] == ["task_001_001_001"]
    work = inventory.work_items[0]
    assert work["commit_ids"] == [direct]
    assert work["review_ids"] == ["7"]
    assert inventory.reviews[0]["description_status"] == "lead_pending_current_code_check"
    commit = next(row for row in inventory.commits if row["commit_id"] == direct)
    assert commit["provenance"] == "reconciliation_receipt"
    assert commit["review_ids"] == ["7"]
    assert f"commit:{direct}" not in {row["row_id"] for row in inventory.ledger}
    assert "work:task_001_001_001" in {row["row_id"] for row in inventory.ledger}
    assert all(row["outcome"] == "unresolved" for row in inventory.ledger)


def test_pin_round_trips_and_records_uncovered_and_unavailable_evidence(
    tmp_path: Path,
) -> None:
    project, baseline, direct = _repository(tmp_path)
    missing = "f" * 40
    receipt_path = project.target.root / "architecture" / "reconciliation-receipts.json"
    state = json.loads(receipt_path.read_text(encoding="utf-8"))
    state["receipts"]["task_001_001_001"][0]["implementation_revisions"].append(missing)
    receipt_path.write_text(json.dumps(state), encoding="utf-8")
    revised = _commit(project.target.root, "add unreachable receipt evidence")

    destination = project.target.root / "inventory.json"
    pinned = pin_historical_inventory(
        project, "feat_034_007", target_revision=revised,
        tracking_revision=revised, path=destination,
    )
    loaded = read_historical_inventory(project, path=destination)

    assert loaded == pinned
    assert any(row["kind"] == "uncovered_commit" for row in loaded.ledger)
    assert not any(
        row["row_id"] == f"commit:{direct}" for row in loaded.ledger
    )
    assert any(
        row["reason"] == "target_commit_unreachable" and missing in row["detail"]
        for row in loaded.unavailable
    )
    payload = destination.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    assert json.loads(payload)["target_baseline"] == revised


def test_authorized_parent_handoff_redacts_unavailable_child_record(
    tmp_path: Path,
) -> None:
    project, baseline, direct = _repository(tmp_path)
    parent_revision = "a" * 40
    handoff = AuthorizedWorkHandoff(
        work_id="task_001_001_001",
        tier="task",
        parent="feat_001_001",
        title="task_001_001_001",
        evidence_revision=None,
        narrative=None,
        completion_evidence={
            "kind": "parent_closeout_lists_completed_child",
            "feature_id": "feat_001_001",
            "feature_revision": parent_revision,
        },
        unavailable_reason="task_record_not_read_under_epic_scope",
    )

    inventory = build_historical_inventory(
        project,
        "feat_034_007",
        target_revision=baseline,
        tracking_revision=baseline,
        authorized_work_handoffs=(handoff,),
        authorized_review_handoffs=(AuthorizedReviewHandoff(
            review_id="218",
            url="https://github.example/acme/repo/pull/218",
            forge="github",
            work_ids=("task_001_001_001",),
            acceptance_status="open_not_accepted_at_handoff",
            status_evidence_revision=parent_revision,
        ),),
    )

    work = next(
        row for row in inventory.work_items
        if row["work_id"] == "task_001_001_001"
    )
    assert work["evidence_revision"] is None
    assert work["repository_path"] is None
    assert work["narrative"] is None
    assert work["commit_ids"] == [direct]
    assert work["review_ids"] == ["7", "218"]
    ledger = next(
        row for row in inventory.ledger
        if row["row_id"] == "work:task_001_001_001"
    )
    assert ledger["revision"] is None
    assert ledger["evidence_revisions"] == [direct]
    assert ledger["review_ids"] == ["7", "218"]
    assert ledger["completion_evidence"] == {
        "kind": "parent_closeout_lists_completed_child",
        "feature_id": "feat_001_001",
        "feature_revision": parent_revision,
    }
    assert ledger["unavailable_reason"] == (
        "task_record_not_read_under_epic_scope"
    )
    assert any(
        row["reason"] == "task_record_not_read_under_epic_scope"
        and row["detail"] == "task_001_001_001"
        for row in inventory.unavailable
    )
    review = next(row for row in inventory.reviews if row["review_id"] == "218")
    assert review["acceptance_status"] == "open_not_accepted_at_handoff"
    assert review["status_evidence_revision"] == parent_revision
    assert review["source_revision_status"] == "unavailable"


def test_pinned_inventory_contains_authorized_a_f_handoff() -> None:
    root = Path(__file__).parents[2]
    path = root / (
        "architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/"
        "historical-evidence-inventory.json"
    )
    inventory = json.loads(path.read_text(encoding="utf-8"))
    handoff_revision = "ac60fb982e219888aaeb7533baec07b9059ea82b"
    children = [
        row for row in inventory["ledger"]
        if row.get("completion_evidence", {}).get("kind")
        == "parent_closeout_lists_completed_child"
    ]
    features = [
        row for row in inventory["ledger"]
        if row.get("completion_evidence", {}).get("kind")
        == "epic_owner_authorized_feature_closeout"
    ]

    assert len(features) == 6
    assert len(children) == 34
    assert all(row["revision"] is None for row in children)
    assert all(
        row["unavailable_reason"] == "task_record_not_read_under_epic_scope"
        for row in children
    )
    assert all(
        row["completion_evidence"]["handoff_revision"] == handoff_revision
        for row in [*features, *children]
    )
    review = next(
        row for row in inventory["reviews"] if row["review_id"] == "218"
    )
    assert review["acceptance_status"] == "open_not_accepted_at_handoff"
    assert review["merge_revision"] is None
    assert review["status_evidence_revision"] == handoff_revision
