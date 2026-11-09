"""Fail-closed semantic bindings for rendered C4 hit targets."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cascade.workspace import (
    C4BindingError,
    validate_hit_target_manifest,
    verify_and_sanitize_hit_targets,
)


def test_binding_manifest_survives_sanitization_and_cache_validation(
    tmp_path: Path,
) -> None:
    workspace = _workspace()
    raw_bindings, raw_svg = _write_inputs(tmp_path)
    sanitized = tmp_path / "bound" / "view.svg"

    bindings = verify_and_sanitize_hit_targets(
        workspace=workspace,
        view_key="view",
        raw_bindings=raw_bindings,
        raw_svg=raw_svg,
        sanitized_svg=sanitized,
        expected_semantic_ids=frozenset({"element.worker", "relationship.reads"}),
    )

    assert [binding.semantic_id for binding in bindings] == [
        "element.worker",
        "relationship.reads",
    ]
    text = sanitized.read_text(encoding="utf-8")
    assert "data-cascade-export-id" in text
    assert "onclick" not in text
    assert "data-cascade-unapproved" not in text
    assert "https://example.invalid" not in text
    assert "<script" not in text

    manifest = {
        "version": 1,
        "interactive": True,
        "source_diff_reference": "revision:abc;paths:architecture/workspace.dsl",
        "views": [
            {
                "view_key": "view",
                "svg": "bound/view.svg",
                "targets": [binding.as_dict() for binding in bindings],
            }
        ],
    }
    assert validate_hit_target_manifest(
        workspace=workspace,
        manifest=manifest,
        artifact_root=tmp_path,
        expected_view_keys=("view",),
        expected_semantic_ids=frozenset({"element.worker", "relationship.reads"}),
    ) == (sanitized,)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "has no modelId"),
        ("stale", "stale semantic ID"),
        ("duplicate", "ambiguous duplicate semantic target"),
        ("cycle", "cyclic semantic identity chain"),
        ("kind", "not captured kind"),
        ("svg", "serialized SVG attributes do not match"),
    ],
)
def test_broken_or_ambiguous_binding_blocks_interaction(
    tmp_path: Path, mutation: str, message: str
) -> None:
    workspace = _workspace()
    raw_bindings, raw_svg = _write_inputs(tmp_path)
    rows = json.loads(raw_bindings.read_text(encoding="utf-8"))
    expected = {"element.worker", "relationship.reads"}
    if mutation == "missing":
        rows[0]["modelId"] = None
    elif mutation == "stale":
        expected.remove("element.worker")
    elif mutation == "duplicate":
        rows[1] = {**rows[0], "rendererNodeId": "node-relationship"}
    elif mutation == "cycle":
        workspace["model"]["elements"][0]["containerId"] = "instance-1"
    elif mutation == "kind":
        rows[0]["kind"] = "relationship"
    elif mutation == "svg":
        rows[0]["modelId"] = "element-1"
    raw_bindings.write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(C4BindingError, match=message):
        verify_and_sanitize_hit_targets(
            workspace=workspace,
            view_key="view",
            raw_bindings=raw_bindings,
            raw_svg=raw_svg,
            sanitized_svg=tmp_path / "sanitized.svg",
            expected_semantic_ids=frozenset(expected),
        )


def _workspace() -> dict[str, object]:
    return {
        "model": {
            "elements": [
                {"id": "instance-1", "containerId": "element-1"},
                {
                    "id": "element-1",
                    "properties": {"cascade.semanticId": "element.worker"},
                },
            ],
            "relationships": [
                {
                    "id": "derived-1",
                    "sourceId": "instance-1",
                    "destinationId": "instance-1",
                    "linkedRelationshipId": "relationship-1",
                },
                {
                    "id": "relationship-1",
                    "sourceId": "element-1",
                    "destinationId": "element-1",
                    "properties": {"cascade.semanticId": "relationship.reads"},
                },
            ],
        }
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    bindings = tmp_path / "bindings.json"
    bindings.write_text(
        json.dumps(
            [
                {
                    "rendererNodeId": "node-element",
                    "kind": "element",
                    "modelId": "instance-1",
                },
                {
                    "rendererNodeId": "node-relationship",
                    "kind": "relationship",
                    "modelId": "derived-1",
                },
            ]
        ),
        encoding="utf-8",
    )
    svg = tmp_path / "raw.svg"
    svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg">
          <script>alert(1)</script>
          <a href="https://example.invalid">external</a>
          <g id="node-element" onclick="bad()" data-cascade-unapproved="x"
             data-cascade-model-kind="element" data-cascade-export-id="instance-1" />
          <path id="node-relationship" data-cascade-model-kind="relationship"
             data-cascade-export-id="derived-1" />
        </svg>""",
        encoding="utf-8",
    )
    return bindings, svg
