import json
import subprocess
from pathlib import Path

from cascade.workspace.c4_source import validate_c4_workspace


ROOT = Path(__file__).resolve().parents[2]
TARGET_KEY = "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
ARCHITECTURE = ROOT / "architecture" / TARGET_KEY


def test_every_python_directory_has_exact_design_ownership() -> None:
    index = json.loads((ROOT / "architecture/design-mappings.json").read_text())
    evidence = json.loads((ARCHITECTURE / "reconstruction-evidence.json").read_text())
    mappings = index["designs"]
    python_directories = {
        path.parent.relative_to(ROOT).as_posix()
        for tree in (ROOT / "cascade", ROOT / "tests")
        for path in tree.rglob("*.py")
    }

    assert index["version"] == 1
    assert index["target_repository_key"] == TARGET_KEY
    assert python_directories <= mappings.keys()
    assert mappings["."]["design_owner_directory"] == "."

    for code_directory, row in mappings.items():
        assert row["code_directory"] == code_directory
        owner = row["design_owner_directory"]
        expected = f"design:{TARGET_KEY}:{owner}"
        assert row["artifact_id"] == expected
        assert (ROOT / owner / "DESIGN.md").is_file()

    for excluded, parent in evidence["directory_coverage"]["excluded"].items():
        assert mappings[excluded]["design_owner_directory"] == parent
        assert parent == "." or Path(parent) in Path(excluded).parents


def test_leaf_designs_have_unique_owned_ids_and_pinned_evidence() -> None:
    evidence = json.loads((ARCHITECTURE / "reconstruction-evidence.json").read_text())
    requirement_ids: set[str] = set()
    decision_ids: set[str] = set()

    for owner in evidence["directory_coverage"]["included"]:
        text = (ROOT / owner / "DESIGN.md").read_text()
        if owner == ".":
            continue
        assert "Purpose:" in text
        assert "Interfaces" in text
        assert "Known gaps:" in text
        assert evidence["inventory"]["target_baseline"] in text
        assert evidence["inventory"]["sha256"] in text
        for token in text.replace("`", " ").split():
            clean = token.strip("(),.;:")
            if clean.startswith("REQ-"):
                assert clean not in requirement_ids
                requirement_ids.add(clean)
            if clean.startswith("DEC-"):
                assert clean not in decision_ids
                decision_ids.add(clean)


def test_c4_contract_has_stable_context_container_and_component_views() -> None:
    contract = validate_c4_workspace(ARCHITECTURE)
    evidence = json.loads((ARCHITECTURE / "reconstruction-evidence.json").read_text())
    inventory = ARCHITECTURE / "historical-evidence-inventory.json"

    assert {view.key for view in contract.views} == {
        "cascade-landscape",
        "cascade-context",
        "cascade-containers",
        "cascade-supervisor-components",
    }
    assert contract.owner == "task_034_007_002"
    assert set(contract.fragment_owners.values()) == {"task_034_007_002"}
    assert len(contract.semantic_ids) == len(contract.elements) + len(contract.relationships)
    inventory_state = json.loads(inventory.read_text())
    assert (
        inventory_state["baseline_pair"]["g_artifact_sha256"]
        == evidence["inventory"]["sha256"]
    )
    assert evidence["target_repository_key"] == TARGET_KEY
    assert evidence["proposal"]["accepted"] is False


def test_staged_evidence_pins_the_authored_design_and_model_bytes() -> None:
    evidence = json.loads((ARCHITECTURE / "reconstruction-evidence.json").read_text())
    revision = evidence["artifact_revision"]
    paths = [
        Path("architecture/design-mappings.json"),
        Path("cascade/workspace/DESIGN.md"),
        Path("architecture") / TARGET_KEY / "workspace.dsl",
        Path("architecture") / TARGET_KEY / "model.dsl",
        Path("architecture") / TARGET_KEY / "views.dsl",
        Path("architecture") / TARGET_KEY / "workspace.contract.json",
    ]

    assert evidence["proposal"]["status"] == "staged_pending_review"
    assert len(evidence["proposal"]["review_unit_ids"]) == 1
    for path in paths:
        pinned = subprocess.check_output(
            ["git", "show", f"{revision}:{path.as_posix()}"], cwd=ROOT
        )
        assert pinned == (ROOT / path).read_bytes()
