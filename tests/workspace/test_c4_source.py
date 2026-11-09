"""Versioned Structurizr source and semantic identity contract."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cascade.workspace import C4SourceError, validate_c4_workspace

_REPOSITORY_ROOT = Path(__file__).parents[2]
_VERSIONED_WORKSPACE = (
    _REPOSITORY_ROOT
    / "architecture"
    / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
)


def test_versioned_workspace_uses_semantics_not_labels_order_or_parallel_edges(
    tmp_path: Path,
) -> None:
    workspace = _copy_workspace(tmp_path)
    manifest_path = workspace / "workspace.contract.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["elements"].reverse()
    manifest["relationships"].reverse()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    model_path = workspace / "model.dsl"
    model = model_path.read_text(encoding="utf-8")
    validates = model.index("validates =")
    exports = model.index("exports =")
    model_path.write_text(
        model[:validates] + model[exports:] + "\n" + model[validates:exports],
        encoding="utf-8",
    )

    contract = validate_c4_workspace(workspace)
    by_dsl_id = {
        item.dsl_identifier: item.semantic_id
        for item in (*contract.elements, *contract.relationships)
    }

    # The two containers intentionally have the same label, and the two edges
    # intentionally share endpoints. Neither label, order, nor endpoint pair is
    # used as identity.
    assert by_dsl_id["supervisor"] != by_dsl_id["structurizr_cli"]
    assert by_dsl_id["validates"] != by_dsl_id["exports"]
    parallel = [
        item
        for item in contract.relationships
        if (item.source, item.destination) == ("supervisor", "structurizr_cli")
    ]
    assert len(parallel) == 2
    assert len(contract.semantic_ids) == len(contract.elements) + len(
        contract.relationships
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("blank_id", "nonempty"),
        ("invalid_id", "valid semantic ID"),
        ("duplicate_id", "duplicate workspace semantic ID"),
        ("missing_property", "exactly one cascade.semanticId"),
        ("duplicate_view", "duplicate view key"),
    ],
)
def test_invalid_semantic_ids_and_view_keys_fail_before_rendering(
    tmp_path: Path, mutation: str, message: str
) -> None:
    workspace = _copy_workspace(tmp_path)
    manifest_path = workspace / "workspace.contract.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if mutation == "blank_id":
        manifest["elements"][0]["semantic_id"] = ""
    elif mutation == "invalid_id":
        manifest["elements"][0]["semantic_id"] = "Element With Spaces"
    elif mutation == "duplicate_id":
        duplicate = manifest["elements"][0]["semantic_id"]
        manifest["elements"][1]["semantic_id"] = duplicate
        model = workspace.joinpath("model.dsl").read_text(encoding="utf-8")
        model = model.replace(
            '"cascade.semanticId" "element.system.cascade"',
            f'"cascade.semanticId" "{duplicate}"',
        )
        workspace.joinpath("model.dsl").write_text(model, encoding="utf-8")
    elif mutation == "missing_property":
        model = workspace.joinpath("model.dsl").read_text(encoding="utf-8")
        model = model.replace(
            '        "cascade.semanticId" "element.person.operator"\n', ""
        )
        workspace.joinpath("model.dsl").write_text(model, encoding="utf-8")
    elif mutation == "duplicate_view":
        views = workspace.joinpath("views.dsl").read_text(encoding="utf-8")
        views += '\nsystemLandscape "cascade-landscape" {\n    include *\n}\n'
        workspace.joinpath("views.dsl").write_text(views, encoding="utf-8")

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(C4SourceError, match=message):
        validate_c4_workspace(workspace)


def test_source_closure_requires_owned_local_non_executable_fragments(
    tmp_path: Path,
) -> None:
    workspace = _copy_workspace(tmp_path)
    workspace.joinpath("workspace.dsl").write_text(
        '!include "https://example.test/model.dsl"\n', encoding="utf-8"
    )

    with pytest.raises(C4SourceError, match="remote C4 references are forbidden"):
        validate_c4_workspace(workspace)


def test_dynamic_occurrences_fail_with_visible_identity_guidance(
    tmp_path: Path,
) -> None:
    workspace = _copy_workspace(tmp_path)
    views = workspace.joinpath("views.dsl").read_text(encoding="utf-8")
    views += '\ndynamic cascade "request-flow" {\n    operator -> cascade "Uses"\n}\n'
    workspace.joinpath("views.dsl").write_text(views, encoding="utf-8")

    with pytest.raises(C4SourceError, match="dynamic views are unsupported"):
        validate_c4_workspace(workspace)


def test_implied_relationships_fail_with_visible_source_identity_guidance(
    tmp_path: Path,
) -> None:
    workspace = _copy_workspace(tmp_path)
    source = workspace.joinpath("workspace.dsl").read_text(encoding="utf-8")
    workspace.joinpath("workspace.dsl").write_text(
        source.replace("!impliedRelationships false", "!impliedRelationships true"),
        encoding="utf-8",
    )

    with pytest.raises(C4SourceError, match="derived relationships are unsupported"):
        validate_c4_workspace(workspace)


def test_rename_continuity_requires_an_explicit_reviewer(tmp_path: Path) -> None:
    workspace = _copy_workspace(tmp_path)
    manifest_path = workspace / "workspace.contract.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["renames"] = [
        {
            "old_semantic_id": "element.person.reviewer",
            "new_semantic_id": "element.person.operator",
            "reviewed_by": "",
        }
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(C4SourceError, match="reviewed_by must be a nonempty string"):
        validate_c4_workspace(workspace)


def _copy_workspace(tmp_path: Path) -> Path:
    destination = tmp_path / "architecture"
    shutil.copytree(_VERSIONED_WORKSPACE, destination)
    return destination
