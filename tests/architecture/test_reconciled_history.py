import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_KEY = "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
ARCHITECTURE = ROOT / "architecture" / TARGET_KEY


def _load(name: str) -> dict:
    return json.loads((ARCHITECTURE / name).read_text())


def test_replay_ledger_covers_original_rows_and_accepted_deltas_once() -> None:
    inventory_path = ARCHITECTURE / "historical-evidence-inventory.json"
    inventory = json.loads(inventory_path.read_text())
    ledger = _load("replay-ledger.json")
    rows = ledger["rows"]

    covered_commits = {
        commit_id
        for work in inventory["work_items"]
        for commit_id in work["commit_ids"]
    }
    original = {f"work:{row['work_id']}" for row in inventory["work_items"]}
    original |= {
        f"commit:{row['commit_id']}"
        for row in inventory["commits"]
        if row["commit_id"] not in covered_commits
    }
    accepted = {
        f"delta:{row['merge_revision']}"
        for row in inventory["baseline_pair"]["integrations"]
    } | {
        f"delta:{row['revision']}"
        for row in inventory["baseline_pair"]["accepted_deltas"]
    }
    expected = original | accepted

    assert ledger["version"] == 2
    assert ledger["target_repository_key"] == TARGET_KEY
    assert ledger["inventory_sha256"] == hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    assert len(original) == 2023
    assert len(accepted) == 16
    assert len(rows) == len(expected) == 2039
    assert {row["row_id"] for row in rows} == expected
    assert all(row["disposition"] in {"durable", "superseded", "no-impact", "unresolved"} for row in rows)
    assert all(row["rationale"] and row["row_id"] in row["rationale"] for row in rows)
    assert all(row["current_code_references"] or row["current_test_references"] for row in rows)
    assert all(
        row["affected_requirement_ids"]
        or row["affected_design_ids"]
        or row["affected_model_ids"]
        for row in rows
    )
    assert ledger["coverage_accounting"] == {
        "original_expected": 2023,
        "original_covered": 2023,
        "accepted_delta_expected": 16,
        "accepted_delta_covered": 16,
        "total_expected": 2039,
        "total_covered": 2039,
        "duplicate_rows": 0,
        "missing_rows": 0,
        "dispositions": {
            "durable": 4,
            "no-impact": 14,
            "superseded": 0,
            "unresolved": 2021,
        },
        "material_unresolved": 2021,
    }
    references = {
        (reference["revision"], reference["repository_path"])
        for row in rows
        for field in ("current_code_references", "current_test_references")
        for reference in row[field]
    }
    for revision, repository_path in references:
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}:{repository_path}"],
            cwd=ROOT,
            check=True,
        )


def test_ledger_references_canonical_evidence_without_double_counting() -> None:
    inventory = _load("historical-evidence-inventory.json")
    ledger = _load("replay-ledger.json")
    rows = {row["row_id"]: row for row in ledger["rows"]}
    review_ids = {review["review_id"] for review in inventory["reviews"]}

    for work in inventory["work_items"]:
        row = rows[f"work:{work['work_id']}"]
        assert row["evidence_revisions"] == ([work["evidence_revision"]] if work["evidence_revision"] else [])
        assert set(row["review_references"]) <= review_ids
        if work.get("unavailable_reason"):
            assert row["unavailable_reason"] == work["unavailable_reason"]

    for commit in inventory["commits"]:
        row = rows[f"commit:{commit['commit_id']}"]
        assert row["evidence_revisions"] == [commit["commit_id"]]
        assert row["review_references"] == commit["review_ids"]
        assert set(row["review_references"]) <= review_ids

    pending_children = [
        row for row in ledger["rows"]
        if row.get("unavailable_reason") == (
            "exact child content/revision unavailable to Epic reader under dec_013; "
            "owner response not yet received; retrieval failure at owner not established"
        )
    ]
    assert len(pending_children) == 34
    assert ledger["evidence_index"] == {
        "commits": "historical-evidence-inventory.json#/commits",
        "reviews": "historical-evidence-inventory.json#/reviews",
        "work_items": "historical-evidence-inventory.json#/work_items",
    }


def test_reconciliation_preserves_pin_and_accounts_for_g_source_delta() -> None:
    report = _load("reconciliation-report.json")
    original = report["g_source_inventory_pin"]["target_revision"]
    refreshed = report["refreshed_g_source_baseline"]["target_revision"]
    actual = subprocess.check_output(
        ["git", "rev-list", "--reverse", f"{original}..{refreshed}"], cwd=ROOT, text=True
    ).splitlines()

    assert report["g_source_delta"]["target_commits"] == actual
    assert {row["work_id"] for row in report["g_source_delta"]["work_items"]} == {
        "task_034_007_001",
        "task_034_007_002",
    }
    assert report["feature_f"]["reachable_on_g_source_inventory_pin"] is True
    assert report["feature_f"]["reachable_on_accepted_epic_pin"] is True
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", report["feature_f"]["implementation_revision"], original],
        cwd=ROOT,
        check=True,
    )
    accepted_epic = report["accepted_epic_pin"]
    assert accepted_epic["feature_f_implementation_reachable"] is True
    assert accepted_epic["feature_g_implementation_reachable"] is True
    present = subprocess.run(
        [
            "git",
            "cat-file",
            "-e",
            f'{accepted_epic["target_revision"]}:cascade/workspace/architecture_context.py',
        ],
        cwd=ROOT,
    )
    assert present.returncode == 0
    assert report["review_state"]["accepted_revision_ids"] == []
    assert report["review_state"]["pending_revision_ids"]
    assert report["closeout_claimed"] is False


def test_parent_edits_are_staged_at_their_exact_revision() -> None:
    report = _load("reconciliation-report.json")
    store = json.loads((ROOT / "architecture/review-units.json").read_text())
    pending = report["review_state"]["pending_review_unit_ids"]
    task_rows = [
        store["review_units"][unit_id]
        for unit_id in pending
        if store["review_units"][unit_id]["owner_work_id"] == "task_034_007_003"
    ]

    assert {row["design"]["reference"]["repository_path"] for row in task_rows} == {
        "DESIGN.md",
        "cascade/DESIGN.md",
    }
    assert {row["design"]["reference"]["revision"] for row in task_rows} == {
        "a911fb1e13729ebce182383a52b3f9832428b535"
    }
    assert {row["status"] for row in task_rows} == {"staged"}
    for row in task_rows:
        reference = row["design"]["reference"]
        pinned = subprocess.check_output(
            ["git", "show", f"{reference['revision']}:{reference['repository_path']}"], cwd=ROOT
        )
        assert hashlib.sha256(pinned).hexdigest() == row["design"]["content_digest"]


def test_requirement_and_decision_ids_have_one_design_home() -> None:
    evidence = _load("reconstruction-evidence.json")
    homes: dict[str, Path] = {}
    pattern = re.compile(r"\b(?:REQ|DEC)-[A-Z0-9-]+\b")

    for owner in evidence["directory_coverage"]["included"]:
        path = ROOT / owner / "DESIGN.md"
        for identifier in pattern.findall(path.read_text()):
            assert identifier not in homes, f"{identifier} is defined by both {homes.get(identifier)} and {path}"
            homes[identifier] = path

    assert homes["REQ-ROOT-002"] == ROOT / "DESIGN.md"
    assert homes["REQ-BOARD-001"] == ROOT / "cascade/board/DESIGN.md"
    assert homes["DEC-WORKSPACE-001"] == ROOT / "cascade/workspace/DESIGN.md"


def test_reconciliation_keeps_direct_mr_overlap_and_unavailable_provenance_honest() -> None:
    inventory = _load("historical-evidence-inventory.json")
    ledger = _load("replay-ledger.json")
    report = _load("reconciliation-report.json")
    rows = {row["row_id"]: row for row in ledger["rows"]}

    direct = rows["commit:9b748ad5568167263ba56d11ab4654097f8d1672"]
    assert direct["disposition"] == "durable"
    assert {ref["repository_path"] for ref in direct["current_test_references"]} == {
        "tests/task/test_worktree.py",
        "tests/war_room/test_http_read.py",
    }

    feature = rows["work:feat_034_006"]
    integration = rows["delta:d2ed1aca886e61d087fa29842ebca617c0956d96"]
    assert feature["disposition"] == integration["disposition"] == "durable"
    assert "review:218" in feature["evidence_keys"]
    assert "review:218" in integration["evidence_keys"]
    review = next(row for row in inventory["reviews"] if row["review_id"] == "218")
    assert review["description_sha256"] == report["evidence_checks"][
        "mr_described_change"
    ]["review_description_sha256"]
    assert review["description_provenance"] == "current_snapshot"
    assert "description_at_merge_time" in review["unavailable_fields"]
    assert report["evidence_checks"]["overlapping_evidence"]["row_ids"] == [
        feature["row_id"], integration["row_id"]
    ]

    unavailable = [row for row in ledger["rows"] if row.get("material_gap")]
    assert len(unavailable) == 2021
    assert all(row["disposition"] == "unresolved" for row in unavailable)
    assert all(row["material_gap"]["owner"] for row in unavailable)
    assert report["closeout_claimed"] is False


def test_reconciliation_reuses_only_exact_staged_owner_proposals() -> None:
    report = _load("reconciliation-report.json")
    store = json.loads((ROOT / "architecture/review-units.json").read_text())

    assert report["proposal_outcome"] == {
        "new_owner_amendments": 0,
        "pending_exact_revision_review": True,
        "reason": (
            "The accepted deltas are lifecycle/plan-only or integrate the "
            "already-staged Feature F/G architecture changes. Reusing the exact "
            "pending owner-scoped units avoids a second store and duplicate proposals."
        ),
        "stable_c4_ids_changed": [],
    }
    assert {row["review_unit_id"] for row in report["design_proposals"]} == set(
        store["review_units"]
    )
    assert {row["status"] for row in report["design_proposals"]} == {"staged"}
