import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from cascade.workspace import build_acceptance_summary


ROOT = Path(__file__).resolve().parents[2]
TARGET_KEY = "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
ARCHITECTURE = ROOT / "architecture" / TARGET_KEY


def _load(name: str) -> dict:
    return json.loads((ARCHITECTURE / name).read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_delta_refreshes_the_exact_accepted_epic_pair() -> None:
    report = _load("final-validation-report.json")
    start = report["baseline_pair"]["previous_accepted_target"]
    end = report["baseline_pair"]["target_revision"]
    actual = subprocess.check_output(
        ["git", "rev-list", "--reverse", f"{start}..{end}"], cwd=ROOT, text=True
    ).splitlines()

    assert [row["revision"] for row in report["accepted_deltas_after_reconciliation"]] == actual
    assert report["baseline_pair"]["target_revision"] == report["baseline_pair"][
        "tracking_revision"
    ]
    assert report["coverage_accounting"]["refreshed_accepted_delta_covered"] == len(actual) == 4
    assert report["baseline_pair"]["corrective_feature_reachable"] is False


def test_f_and_g_are_reachable_from_the_refreshed_accepted_epic() -> None:
    report = _load("final-validation-report.json")
    baseline = report["baseline_pair"]

    assert baseline["feature_f_reachable"] is True
    assert baseline["feature_g_reachable"] is True
    for key in ("feature_f_implementation_revision", "feature_g_implementation_revision"):
        assert subprocess.run(
            ["git", "merge-base", "--is-ancestor", baseline[key], baseline["target_revision"]],
            cwd=ROOT,
        ).returncode == 0


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
    ledger = _load("replay-ledger.json")

    assert report["clean_closeout"] is False
    assert report["outcome"] == "acceptance_pending_with_material_mismatch"
    assert {row["status"] for row in report["architecture_reviews"]} == {"staged"}
    assert all(row["accepted_revision_id"] is None for row in report["architecture_reviews"])
    assert ledger["coverage_accounting"]["material_unresolved"] == 2021
    assert report["coverage_accounting"]["material_unresolved"] == 2021
    assert {gate["code"] for gate in report["receipt_validations"]} == {
        "missing_reconciliation"
    }
    assert report["historical_missing_receipts"][0]["count"] == 78
    assert {row["outcome"] for row in report["blockers"]} == {
        "acceptance_pending", "missing_evidence", "material_mismatch"
    }
    assert all(row["owner"] and row["prerequisite"] for row in report["blockers"])

    expected_artifacts = {
        row["name"]: {"revision": row["revision"], "sha256": row["sha256"]}
        for row in report["artifact_revisions"]
    }
    verified = build_acceptance_summary(
        owner_work_id=report["owner_work_id"],
        baseline_pair=report["baseline_pair"],
        expected_target_revision=report["inspected_revisions"]["accepted_epic_target"],
        expected_tracking_revision=report["inspected_revisions"]["accepted_epic_tracking"],
        artifacts=report["artifact_revisions"],
        required_artifacts=(
            "historical-evidence-inventory.json",
            "replay-ledger.json",
            "reconciliation-report.json",
            "architecture/review-units.json",
        ),
        expected_artifacts=expected_artifacts,
        architecture_reviews=report["architecture_reviews"],
        receipt_validations=report["receipt_validations"],
        coverage_accounting=report["coverage_accounting"],
        accepted_deltas=report["accepted_deltas_after_reconciliation"],
        historical_missing_receipts=report["historical_missing_receipts"],
    )
    assert verified["clean_closeout"] is False
    assert {row["outcome"] for row in verified["blockers"]} == {
        "acceptance_pending", "missing_evidence", "material_mismatch"
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


def test_acceptance_summary_pins_artifact_bytes_and_review_units() -> None:
    report = _load("final-validation-report.json")
    expected = {
        "historical-evidence-inventory.json": ARCHITECTURE / "historical-evidence-inventory.json",
        "replay-ledger.json": ARCHITECTURE / "replay-ledger.json",
        "reconciliation-report.json": ARCHITECTURE / "reconciliation-report.json",
        "architecture/review-units.json": ROOT / "architecture/review-units.json",
    }

    for artifact in report["artifact_revisions"]:
        assert _sha256(expected[artifact["name"]]) == artifact["sha256"]
        subprocess.run(
            ["git", "cat-file", "-e", f'{artifact["revision"]}^{{commit}}'],
            cwd=ROOT,
            check=True,
        )
    store = json.loads((ROOT / "architecture/review-units.json").read_text())
    for review in report["architecture_reviews"]:
        stored = store["review_units"][review["review_unit_id"]]
        assert stored["status"] == review["status"]
        assert stored["design"]["reference"]["revision"] == review["artifact_revision"]
