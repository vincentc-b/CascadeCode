"""Pinned completed-work and target-history inventory."""

from __future__ import annotations

import json
import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace.historical_inventory import (
    AuthorizedReviewHandoff,
    AuthorizedWorkHandoff,
    BaselinePair,
    OwnerEvidenceHandoff,
    ReviewEvidence,
    build_historical_inventory,
    pin_historical_inventory,
    read_historical_inventory,
)
from cascade.workspace.errors import WorkspaceError
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
        row["unavailable_reason"] == (
            "exact child content/revision unavailable to Epic reader under dec_013; "
            "owner response not yet received; retrieval failure at owner not established"
        )
        for row in children
    )
    assert all(
        row["completion_evidence"]["handoff_revision"] == handoff_revision
        for row in [*features, *children]
    )
    assert len(inventory["owner_evidence_handoffs"]) == 34
    request_ids = {
        "feat_034_001": "epic_034:epic034-h-evidence-feat_034_001-20261110T1713",
        "feat_034_002": "epic_034:epic034-h-evidence-feat_034_002-20261110T1713",
        "feat_034_003": "epic_034:epic034-h-evidence-feat_034_003-20261110T1713",
        "feat_034_004": "epic_034:epic034-h-evidence-feat_034_004-20261110T1713",
        "feat_034_005": "epic_034:epic034-h-evidence-feat_034_005-20261110T1713",
        "feat_034_006": "epic_034:epic034-h-evidence-feat_034_006-20261110T1713",
    }
    assert all(
        row["availability"] == "pending_owner_handoff"
        and row["record_revision"] is None
        and row["source_repository"] is None
        and row["source_path"] is None
        and row["responsible_owner"] == row["owning_feature"]
        and row["owner_request_id"] == request_ids[row["owning_feature"]]
        for row in inventory["owner_evidence_handoffs"]
    )
    baseline = inventory["baseline_pair"]
    assert baseline["target_revision"] == baseline["tracking_revision"] == (
        "2c5476fabf83a0b0eb996d3ad53b22fdf31321b9"
    )
    assert baseline["g_artifact_revision"] == (
        "e3c5e3126b63bef102d4d85cf7ac68f5974daeb4"
    )
    assert [row["work_id"] for row in baseline["integrations"]] == [
        "feat_034_006", "feat_034_007",
    ]
    assert len(baseline["accepted_deltas"]) == 14
    review = next(
        row for row in inventory["reviews"] if row["review_id"] == "218"
    )
    assert review["acceptance_status"] == "merged_reachable_from_accepted_target"
    assert review["merge_revision"] == (
        "d2ed1aca886e61d087fa29842ebca617c0956d96"
    )
    assert review["description_provenance"] == "current_snapshot"
    assert "description_at_merge_time" in review["unavailable_fields"]


def test_versioned_baseline_owner_and_review_evidence_are_pinned_together(
    tmp_path: Path,
) -> None:
    project, baseline, direct = _repository(tmp_path)
    artifact_path = "architecture/g-inventory.json"
    artifact = project.target.root / artifact_path
    artifact.write_bytes(b'{"version":1}\n')
    g_pin = _commit(project.target.root, "pin G artifact")
    _git(project.target.root, "checkout", "-b", "feature-evidence")
    (project.target.root / "feature.txt").write_text("feature\n", encoding="utf-8")
    head = _commit(project.target.root, "feature evidence")
    _git(project.target.root, "checkout", "main")
    _git(
        project.target.root,
        "merge",
        "--no-ff",
        "feature-evidence",
        "-m",
        "merge feature evidence",
    )
    accepted = _git(project.target.root, "rev-parse", "HEAD")
    repository_key = project.target_repository_key
    pair = BaselinePair(
        target_repository_key=repository_key,
        target_revision=accepted,
        tracking_repository_key=repository_key,
        tracking_revision=accepted,
        g_artifact_repository_key=repository_key,
        g_artifact_repository_role="target",
        g_artifact_path=artifact_path,
        g_artifact_revision=g_pin,
        g_artifact_sha256=hashlib.sha256(b'{"version":1}\n').hexdigest(),
        integrations=({
            "work_id": "feat_001_001",
            "review_id": "99",
            "head_revision": head,
            "base_revision": g_pin,
            "merge_revision": accepted,
        },),
    )
    description = "Current forge description; not proven merge-time text."

    inventory = build_historical_inventory(
        project,
        "feat_034_008",
        baseline_pair=pair,
        owner_evidence_handoffs=(OwnerEvidenceHandoff(
            work_id="task_001_001_001",
            owning_feature="feat_001_001",
            authorized_source="epic_handoff:req-1",
            availability="available",
            record_revision=baseline,
            intent_excerpt="Deliver the direct fix.",
            intent_source_reference="task body:goal",
            verification_excerpt="Direct fix verified.",
            verification_source_reference="task body:done when",
        ),),
        review_evidence=(ReviewEvidence(
            review_id="99",
            forge="github",
            repository_key=repository_key,
            url="https://github.example/acme/repo/pull/99",
            work_ids=("task_001_001_001",),
            captured_at="2026-11-10T17:00:00Z",
            description=description,
            description_sha256=hashlib.sha256(description.encode()).hexdigest(),
            description_provenance="current_snapshot",
            source_revision=head,
            head_revision=head,
            base_revision=g_pin,
            merge_revision=accepted,
            linked_commit_ids=(head, accepted),
            unavailable_fields={
                "description_at_merge_time": (
                    "no immutable merge-time description archive"
                ),
            },
        ),),
    )

    assert inventory.version == 2
    assert inventory.baseline_pair == pair
    assert BaselinePair.from_dict(pair.to_dict()) == pair
    assert inventory.target_baseline == accepted
    handoff = inventory.owner_evidence_handoffs[0]
    assert OwnerEvidenceHandoff.from_dict(handoff).to_dict() == handoff
    assert handoff["record_revision"] == baseline
    work = inventory.work_items[0]
    assert work["owner_evidence_handoff"] == handoff
    review = next(row for row in inventory.reviews if row["review_id"] == "99")
    assert review["description_sha256"] == hashlib.sha256(
        description.encode()
    ).hexdigest()
    assert review["description_status"] == "captured_current_description"
    assert review["acceptance_status"] == "merged_reachable_from_accepted_target"
    assert ReviewEvidence.from_dict(review).description == description

    with pytest.raises(WorkspaceError, match="content hash mismatch"):
        build_historical_inventory(
            project,
            "feat_034_008",
            baseline_pair=replace(pair, g_artifact_sha256="0" * 64),
        )


def test_unavailable_owner_evidence_requires_null_revision_reason_and_owner() -> None:
    with pytest.raises(WorkspaceError, match="reason or owner"):
        # Validation occurs at the inventory boundary, not by trusting a
        # partially populated handoff object.
        _validate_owner_handoff_for_test(OwnerEvidenceHandoff(
            work_id="task_034_001_001",
            owning_feature="feat_034_001",
            authorized_source="epic_handoff:req-2",
            availability="unavailable",
            record_revision=None,
            unavailable_reason="owner archive unavailable",
        ))


def test_pending_owner_evidence_requires_request_and_has_no_received_source() -> None:
    pending = OwnerEvidenceHandoff(
        work_id="task_034_001_001",
        owning_feature="feat_034_001",
        authorized_source="epic_handoff:routing-relay",
        availability="pending_owner_handoff",
        record_revision=None,
        unavailable_reason="owner response not yet received",
        responsible_owner="feat_034_001",
    )
    with pytest.raises(WorkspaceError, match="lacks request id"):
        _validate_owner_handoff_for_test(pending)
    with pytest.raises(WorkspaceError, match="unreceived source"):
        _validate_owner_handoff_for_test(replace(
            pending,
            owner_request_id="epic_034:request-1",
            source_repository="unreceived/repository",
        ))

    validated = replace(pending, owner_request_id="epic_034:request-1")
    assert _validate_owner_handoff_for_test(validated) is None


def _validate_owner_handoff_for_test(handoff: OwnerEvidenceHandoff) -> None:
    # Keep the assertion on the public build operation while avoiding another
    # repository fixture solely for malformed input.
    from cascade.workspace.historical_inventory import _validate_owner_evidence_handoffs

    _validate_owner_evidence_handoffs((handoff,))
