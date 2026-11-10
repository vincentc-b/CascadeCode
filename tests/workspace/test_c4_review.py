"""Pinned paired C4 review payload and changed-view inventory."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.workspace import (
    C4Element,
    C4RenderArtifact,
    C4SemanticDiff,
    C4SemanticModelArtifact,
    C4View,
    C4ViewDiff,
    C4WorkspaceContract,
    ProjectContext,
    WorkspaceError,
    compose_c4_review_payload,
    resolve_c4_review_payload,
)


REVISION_A = "a" * 40
REVISION_B = "b" * 40


def test_payload_pairs_only_exact_key_and_level_and_lists_every_change(
    tmp_path: Path,
) -> None:
    current = _artifact(tmp_path / "current", "current", REVISION_A, ("context", "old"))
    proposed = _artifact(tmp_path / "proposed", "proposed", REVISION_B, ("context", "new"))
    diff = _diff(current, proposed, ("context", "new", "old"))

    payload = compose_c4_review_payload(
        _unit(), diff, owner="feature-team", work_id="feat_034_004",
        current=current, proposed=proposed, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "ready"
    assert payload.changed_views == (
        ("context", "systemContextViews"),
        ("new", "containerViews"),
        ("old", "containerViews"),
    )
    assert [(view.key, view.level, view.current is None, view.proposed is None) for view in payload.views] == [
        ("context", "systemContextViews", False, False),
        ("new", "containerViews", True, False),
        ("old", "containerViews", False, True),
    ]
    assert payload.repositories == (
        {"side": "current", "repository_key": "docs-current", "revision": REVISION_A},
        {"side": "proposed", "repository_key": "docs-proposed", "revision": REVISION_B},
    )
    assert payload.requirements == ("REQ-7",)
    assert payload.decisions == ("ADR-4",)
    assert payload.diffs["source"] == "git:model-a..model-b"
    assert payload.diffs["plan"] == "git:plan-a..plan-b"
    # Only semantic identities reach clients; renderer node and export IDs do not.
    assert payload.views[0].current.targets[0].semantic_id == "element.system"
    assert "renderer_node_id" not in payload.to_dict()["views"][0]["current"]["targets"][0]
    assert 'data-cascade-semantic-id="element.system"' in payload.views[0].current.svg


def test_revision_or_manifest_failure_is_visible_and_keeps_all_diffs(
    tmp_path: Path,
) -> None:
    proposed = _artifact(tmp_path / "proposed", "proposed", REVISION_A, ("context",))
    diff = _diff(None, proposed, ("context",), state="first_model")

    payload = compose_c4_review_payload(
        _unit(proposed_revision=REVISION_B, empty_baseline=True), diff,
        owner="feature-team", work_id="feat_034_004", current=None,
        proposed=proposed, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "error"
    assert "does not match pinned revision" in (payload.error or "")
    assert payload.views == ()
    assert payload.diffs["source"] == "git:model-a..model-b"
    assert payload.diffs["model"]["changed_view_keys"] == ["context"]
    assert payload.diffs["plan"] == "git:plan-a..plan-b"


def test_owner_scope_is_enforced_before_artifacts_are_exposed(tmp_path: Path) -> None:
    proposed = _artifact(tmp_path / "proposed", "proposed", REVISION_B, ("context",))
    diff = _diff(None, proposed, ("context",), state="first_model")

    with pytest.raises(WorkspaceError, match="owner scope"):
        compose_c4_review_payload(
            _unit(empty_baseline=True), diff, owner="another-team",
            work_id="feat_034_004", current=None, proposed=proposed,
            plan_diff_reference="git:plan-a..plan-b",
        )


def test_empty_proposal_is_explicit_and_preserves_pinned_repository() -> None:
    proposed = C4SemanticModelArtifact(
        "proposed", C4RenderArtifact(status="empty", closure_digest="empty", revision=REVISION_B),
        _contract(Path("."), ()),
    )
    diff = C4SemanticDiff(
        "empty_proposal", None, "proposed", "git:model-a..model-b", (), (), (), (),
        "empty proposal", None,
    )

    payload = compose_c4_review_payload(
        _unit(empty_baseline=True), diff, owner="feature-team", work_id="feat_034_004",
        current=None, proposed=proposed, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "removed"
    assert payload.views == ()
    assert payload.repositories == (
        {"side": "proposed", "repository_key": "docs-proposed", "revision": REVISION_B},
    )


@pytest.mark.parametrize("baseline_state, expected", [("first_model", "first"), ("empty_baseline", "empty")])
def test_first_and_empty_baseline_states_are_explicit(
    tmp_path: Path, baseline_state: str, expected: str
) -> None:
    proposed = _artifact(tmp_path / "proposed", "proposed", REVISION_B, ("context",))
    current = None
    if baseline_state == "empty_baseline":
        current = C4SemanticModelArtifact(
            "empty", C4RenderArtifact(status="empty", closure_digest="empty"),
            _contract(tmp_path, ()),
        )
    diff = _diff(current, proposed, ("context",), state=baseline_state)

    payload = compose_c4_review_payload(
        _unit(empty_baseline=True), diff, owner="feature-team", work_id="feat_034_004",
        current=current, proposed=proposed, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == expected
    assert payload.changed_views == (("context", "systemContextViews"),)


def test_semantic_render_error_never_falls_back_to_static_artifacts(tmp_path: Path) -> None:
    proposed = _artifact(tmp_path / "proposed", "proposed", REVISION_B, ("context",))
    valid = _diff(None, proposed, ("context",), state="first_model")
    diff = C4SemanticDiff(
        "render_error", valid.current_artifact_ref, valid.proposed_artifact_ref,
        valid.source_diff_reference, (), (), valid.views, valid.changed_view_keys,
        "render failed", "ambiguous semantic binding",
    )

    payload = compose_c4_review_payload(
        _unit(empty_baseline=True), diff, owner="feature-team", work_id="feat_034_004",
        current=None, proposed=proposed, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "error"
    assert payload.views == ()
    assert payload.error == "ambiguous semantic binding"
    assert payload.diffs["source"] == "git:model-a..model-b"


def test_unchanged_review_is_explicit_and_keeps_the_pinned_pair(tmp_path: Path) -> None:
    current = _artifact(tmp_path / "current", "current", REVISION_A, ("context",))
    proposed = _artifact(tmp_path / "proposed", "proposed", REVISION_B, ("context",))
    diff = C4SemanticDiff(
        "unchanged", current.artifact_ref, proposed.artifact_ref,
        "git:model-a..model-b", (), (),
        (C4ViewDiff("context", "unchanged"),), (), "no diagram changes", None,
    )

    payload = compose_c4_review_payload(
        _unit(), diff, owner="feature-team", work_id="feat_034_004",
        current=current, proposed=proposed,
        plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "unchanged"
    assert payload.changed_views == ()
    assert payload.views[0].state == "unchanged"
    assert payload.views[0].current.repository_key == "docs-current"
    assert payload.views[0].proposed.repository_key == "docs-proposed"


def test_explicit_no_diagram_change_needs_no_model_artifacts() -> None:
    unit = _unit(empty_baseline=True)
    unit.architecture_impact = "no_diagram_change"
    unit.impact_reason = "Only explanatory plan text changed"
    unit.proposed_model = None
    diff = C4SemanticDiff(
        "unchanged", None, None, "plan:" + REVISION_B,
        (), (), (), (), "explicitly unchanged", None,
    )

    payload = compose_c4_review_payload(
        unit, diff, owner="feature-team", work_id="feat_034_004",
        current=None, proposed=None, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "no_diagram_change"
    assert payload.reason == "Only explanatory plan text changed"


def test_claimed_diagram_change_with_missing_evidence_is_not_no_change() -> None:
    diff = C4SemanticDiff(
        "unchanged", None, None, "git:model-a..model-b",
        (), (), (), (), "no semantic changes", None,
    )

    payload = compose_c4_review_payload(
        _unit(), diff, owner="feature-team", work_id="feat_034_004",
        current=None, proposed=None, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.state == "error"
    assert "no corresponding rendered artifact" in (payload.error or "")


def test_semantic_inventory_has_side_state_and_deterministic_drill_choices(
    tmp_path: Path,
) -> None:
    current = _artifact(tmp_path / "current", "current", REVISION_A, ("context",))
    proposed = _artifact(
        tmp_path / "proposed", "proposed", REVISION_B, ("context", "detail")
    )
    diff = C4SemanticDiff(
        "changed", "current", "proposed", "git:model-a..model-b", (), (),
        (
            C4ViewDiff(
                "context", "unchanged",
                current_elements=("element.system",),
                proposed_elements=("element.system",),
            ),
            C4ViewDiff(
                "detail", "added", proposed_elements=("element.system",),
                changed_identities=("element.system",),
            ),
        ),
        ("detail",), "one affected view", None,
    )

    payload = compose_c4_review_payload(
        _unit(), diff, owner="feature-team", work_id="feat_034_004",
        current=current, proposed=proposed, plan_diff_reference="git:plan-a..plan-b",
    )

    assert payload.targets[0].semantic_id == "element.system"
    assert payload.targets[0].current == "present"
    assert payload.targets[0].proposed == "present"
    assert payload.targets[0].drill_choices == (
        {"view_key": "context", "level": "systemContextViews", "label": "context (systemContextViews)"},
        {"view_key": "detail", "level": "containerViews", "label": "detail (containerViews)"},
    )
    assert payload.views[1].current_state == "absent"
    assert payload.views[1].proposed_state == "present"


def test_resolver_returns_actionable_missing_review_with_lineage_provenance(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)

    payload = resolve_c4_review_payload(
        ProjectContext.colocated(tmp_path), owner="feature_architect",
        work_id="feat_046_001", lineage="epic_046",
    )

    assert payload.state == "missing_review"
    assert payload.reason_code == "missing_review"
    assert "published" in (payload.reason or "")
    assert payload.provenance["code"]["accepted_revision"] is None


def _unit(*, proposed_revision: str = REVISION_B, empty_baseline: bool = False) -> SimpleNamespace:
    current = None if empty_baseline else _binding("docs-current", REVISION_A)
    return SimpleNamespace(
        authorized_owner="feature-team",
        owner_work_id="feat_034_004",
        review_unit_id="architecture-review-exact",
        reviewed_tuple_digest="exact",
        requirement_citations=("REQ-7",),
        decision_citations=("ADR-4",),
        proposed_model=_binding("docs-proposed", proposed_revision),
        accepted_baseline=SimpleNamespace(model=current),
    )


def _binding(repository: str, revision: str) -> SimpleNamespace:
    reference = SimpleNamespace(destination_repository_key=repository, revision=revision)
    return SimpleNamespace(contract=SimpleNamespace(reference=reference))


def _artifact(
    root: Path, artifact_ref: str, revision: str, view_keys: tuple[str, ...]
) -> C4SemanticModelArtifact:
    root.mkdir(parents=True)
    workspace = {
        "model": {"softwareSystems": [{
            "id": "1", "properties": {"cascade.semanticId": "element.system"},
        }]},
        "views": {
            "systemContextViews": [
                {"key": key, "elements": [{"id": "1"}]}
                for key in view_keys if key == "context"
            ],
            "containerViews": [
                {"key": key, "elements": [{"id": "1"}]}
                for key in view_keys if key != "context"
            ],
        },
    }
    workspace_path = root / "workspace.json"
    workspace_path.write_text(json.dumps(workspace), encoding="utf-8")
    rows = []
    svg_files = []
    for index, key in enumerate(sorted(view_keys)):
        svg = root / f"view-{index}.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><g id="node-1" '
            'data-cascade-model-kind="element" data-cascade-export-id="1" /></svg>',
            encoding="utf-8",
        )
        svg_files.append(svg)
        rows.append({
            "view_key": key,
            "svg": svg.name,
            "targets": [{
                "view_key": key, "renderer_node_id": "node-1", "kind": "element",
                "export_id": "1", "semantic_id": "element.system",
            }],
        })
    manifest = root / "hit-targets.json"
    manifest.write_text(json.dumps({
        "version": 1, "interactive": True,
        "source_diff_reference": "git:model-a..model-b", "views": rows,
    }), encoding="utf-8")
    render = C4RenderArtifact(
        status="ready", closure_digest=artifact_ref, artifact_directory=root,
        semantic_workspace=workspace_path,
        semantic_workspace_sha256=hashlib.sha256(workspace_path.read_bytes()).hexdigest(),
        svg_files=tuple(svg_files), binding_manifest=manifest, interactive=True,
        source_diff_reference="git:model-a..model-b", view_keys=tuple(sorted(view_keys)),
        revision=revision,
    )
    return C4SemanticModelArtifact(artifact_ref, render, _contract(root, view_keys))


def _contract(root: Path, keys: tuple[str, ...]) -> C4WorkspaceContract:
    return C4WorkspaceContract(
        root, Path("workspace.dsl"), "test", {},
        (C4Element("system", "element.system", Path("model.dsl")),), (),
        tuple(C4View(key, Path("views.dsl")) for key in keys), (),
    )


def _diff(
    current: C4SemanticModelArtifact | None,
    proposed: C4SemanticModelArtifact,
    changed: tuple[str, ...],
    *,
    state: str = "changed",
) -> C4SemanticDiff:
    all_keys = sorted(set(current.render.view_keys if current else ()) | set(proposed.render.view_keys))
    views = tuple(
        C4ViewDiff(
            key, "first_model" if state == "first_model" else
            ("added" if current is None or key not in current.render.view_keys else
             "removed_view" if key not in proposed.render.view_keys else "changed")
        )
        for key in all_keys
    )
    return C4SemanticDiff(
        state, current.artifact_ref if current else None, proposed.artifact_ref,
        "git:model-a..model-b", (), (), views, changed, "two affected views", None,
    )
