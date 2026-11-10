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


def test_replay_ledger_covers_work_and_uncovered_commits_once() -> None:
    inventory_path = ARCHITECTURE / "historical-evidence-inventory.json"
    inventory = json.loads(inventory_path.read_text())
    ledger = _load("replay-ledger.json")
    rows = ledger["rows"]

    covered_commits = {
        commit_id
        for work in inventory["work_items"]
        for commit_id in work["commit_ids"]
    }
    expected = {f"work:{row['work_id']}" for row in inventory["work_items"]}
    expected |= {
        f"commit:{row['commit_id']}"
        for row in inventory["commits"]
        if row["commit_id"] not in covered_commits
    }

    assert ledger["version"] == 1
    assert ledger["target_repository_key"] == TARGET_KEY
    assert ledger["inventory_sha256"] == hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    assert len(rows) == len(expected) == 2023
    assert {row["row_id"] for row in rows} == expected
    assert all(row["owner"] == "task_034_007_003" for row in rows)
    assert all(row["disposition"] in {"durable", "superseded", "no-impact", "unresolved"} for row in rows)
    assert all(row["affected_design_paths"] for row in rows)
    assert all("requirement_ids" in row and "decision_ids" in row for row in rows)


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
    assert report["feature_f"]["reachable_on_accepted_epic_pin"] is False
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", report["feature_f"]["implementation_revision"], original],
        cwd=ROOT,
        check=True,
    )
    accepted_epic = report["accepted_epic_pin"]
    assert accepted_epic["feature_f_implementation_reachable"] is False
    assert accepted_epic["feature_f_architecture_context_present"] is False
    missing = subprocess.run(
        [
            "git",
            "cat-file",
            "-e",
            f'{accepted_epic["target_revision"]}:cascade/workspace/architecture_context.py',
        ],
        cwd=ROOT,
    )
    assert missing.returncode != 0
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
