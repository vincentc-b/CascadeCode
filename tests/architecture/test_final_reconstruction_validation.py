import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_KEY = "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
ARCHITECTURE = ROOT / "architecture" / TARGET_KEY


def _load(name: str) -> dict:
    return json.loads((ARCHITECTURE / name).read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_delta_is_exact_and_does_not_promote_tracking_only_work() -> None:
    report = _load("final-validation-report.json")
    start = report["inspected_revisions"]["task_003_refreshed_g_source"]
    end = report["inspected_revisions"]["task_004_start_g_source"]
    actual = subprocess.check_output(
        ["git", "rev-list", "--reverse", f"{start}..{end}"], cwd=ROOT, text=True
    ).splitlines()

    assert report["g_source_delta_since_task_003_refresh"]["target_commits"] == actual
    assert report["g_source_delta_since_task_003_refresh"]["work_items"] == [
        {
            "work_id": "task_034_007_003",
            "implementation_revision": "72e593c4bf059651594533865523d0ce9dd0e3d2",
            "accepted_revision": "6ccef5eea66891a7fdab983ff312598093804254",
            "disposition": "durable_with_pending_owner_review",
        }
    ]
    assert report["g_source_delta_since_task_003_refresh"]["tracking_only"][0][
        "disposition"
    ] == "pending_not_accepted_implementation"
    assert report["feature_f"]["review_description"] == "unavailable"


def test_feature_f_source_reachability_is_not_epic_acceptance() -> None:
    report = _load("final-validation-report.json")
    reconciliation = _load("reconciliation-report.json")
    feature_f = report["feature_f"]
    accepted_epic = reconciliation["accepted_epic_pin"]

    assert feature_f["reachable_on_g_source_inventory_pin"] is True
    assert feature_f["reachable_on_accepted_epic_pin"] is False
    assert accepted_epic["target_revision"] == report["inspected_revisions"]["epic_034_head"]
    assert accepted_epic["review_218_state"] == "open_clean_mergeable_not_merged"
    assert subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            feature_f["implementation_revision"],
            accepted_epic["target_revision"],
        ],
        cwd=ROOT,
    ).returncode != 0


def test_captured_pinned_exports_match_hashes_views_and_stable_model_ids() -> None:
    report = _load("final-validation-report.json")
    validation = report["structurizr_validation"]
    output = ARCHITECTURE / "final-validation"
    workspace = json.loads((output / validation["json"]["path"].split("/", 1)[1]).read_text())
    contract = _load("workspace.contract.json")

    assert validation["status"] == "passed"
    assert _sha256(output / "json/workspace.json") == validation["json"]["sha256"]
    for filename, expected in validation["svg_sha256"].items():
        path = output / "svg" / filename
        assert _sha256(path) == expected
        ET.parse(path)

    exported_views = {
        view["key"]
        for collection in (
            "systemLandscapeViews",
            "systemContextViews",
            "containerViews",
            "componentViews",
        )
        for view in workspace["views"].get(collection, [])
    }
    assert exported_views == set(validation["view_keys"])
    assert exported_views == {view["key"] for view in contract["views"]}

    semantic_ids: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            semantic_id = value.get("properties", {}).get("cascade.semanticId")
            if semantic_id:
                semantic_ids.add(semantic_id)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(workspace["model"])
    contract_ids = {
        row["semantic_id"]
        for collection in ("elements", "relationships")
        for row in contract[collection]
    }
    assert contract_ids <= semantic_ids


def test_final_report_names_every_pending_and_material_gap() -> None:
    report = _load("final-validation-report.json")
    evidence = _load("reconstruction-evidence.json")
    reconciliation = _load("reconciliation-report.json")
    ledger = _load("replay-ledger.json")

    pending = report["artifact_state"]["pending"]
    assert report["clean_closeout"] is False
    assert report["outcome"] == "blocked_pending_review_and_material_provenance_gaps"
    assert len(pending) == 3
    assert reconciliation["review_state"]["pending_review_unit_ids"]
    assert evidence["proposal"]["accepted"] is False
    assert {row["disposition"] for row in ledger["rows"]} == {"unresolved"}

    expected = {
        row["reason"]: row["count"] for row in reconciliation["material_unresolved"]
    }
    actual = {row["reason"]: row["count"] for row in report["artifact_state"]["unresolved"]}
    assert actual == expected
    assert {gate["code"] for gate in report["closeout_validators"].values()} == {
        "missing_reconciliation"
    }


def test_design_heading_references_and_declared_leaf_sections_resolve() -> None:
    evidence = _load("reconstruction-evidence.json")
    root_text = (ROOT / "DESIGN.md").read_text()
    numeric_headings = {
        match.group(1) for match in re.finditer(r"^##+\s+(\d+(?:\.\d+)*)\b", root_text, re.M)
    }
    referenced = set(re.findall(r"§(\d+(?:\.\d+)*)", root_text))

    assert referenced <= numeric_headings
    for owner in evidence["directory_coverage"]["included"]:
        if owner == ".":
            continue
        text = (ROOT / owner / "DESIGN.md").read_text()
        assert "Purpose:" in text
        assert "Evidence:" in text
        assert "Known gaps:" in text


def test_final_scenarios_keep_unknown_provenance_unknown() -> None:
    inventory = _load("historical-evidence-inventory.json")
    ledger = _load("replay-ledger.json")
    report = _load("final-validation-report.json")
    rows = {row["row_id"]: row for row in ledger["rows"]}

    direct = report["focused_scenarios"]["direct_fix"]["example"]
    ambiguous = report["focused_scenarios"]["unavailable_or_ambiguous_provenance"][
        "example"
    ]
    assert rows[direct]["kind"] == "uncovered_commit"
    assert rows[direct]["disposition"] == "unresolved"
    assert rows[ambiguous]["provenance_status"] == "ambiguous"
    assert all(review["description_status"] == "unavailable" for review in inventory["reviews"])
    assert report["focused_scenarios"]["mr_described_non_cascade_change"][
        "status"
    ] == "unavailable"
