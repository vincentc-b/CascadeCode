"""Semantic C4 model and changed-view comparison contract."""

from __future__ import annotations

import json
from pathlib import Path

from cascade.workspace import (
    C4Element,
    C4Relationship,
    C4Rename,
    C4RenderArtifact,
    C4RenderFailure,
    C4SemanticModelArtifact,
    C4View,
    C4WorkspaceContract,
    compute_c4_semantic_diff,
)


def test_layout_and_export_ids_do_not_create_semantic_changes(tmp_path: Path) -> None:
    current = _artifact(tmp_path / "current", export_offset=0, x=10)
    proposed = _artifact(tmp_path / "proposed", export_offset=100, x=900)

    diff = compute_c4_semantic_diff(
        current, proposed, source_diff_reference="git:base..proposal"
    )

    assert diff.state == "unchanged"
    assert diff.changed_view_keys == ()
    assert {item.state for item in diff.identities} == {"unchanged"}
    assert [(view.key, view.state) for view in diff.views] == [("main", "unchanged")]


def test_properties_containment_and_membership_mark_every_affected_view(
    tmp_path: Path,
) -> None:
    current = _artifact(tmp_path / "current")
    proposed = _artifact(
        tmp_path / "proposed",
        description="Changed",
        container_parent=False,
        view_elements=("element.system", "element.container"),
        extra_view=True,
    )

    diff = compute_c4_semantic_diff(
        current, proposed, source_diff_reference="git:base..proposal"
    )

    assert diff.state == "changed"
    changed = {item.semantic_id: item for item in diff.identities}
    assert changed["element.system"].changed_fields == ("properties",)
    assert diff.containment[0].semantic_id == "element.container"
    assert [(view.key, view.state) for view in diff.views] == [
        ("added", "added"),
        ("main", "changed"),
    ]
    assert diff.changed_view_keys == ("added", "main")
    assert diff.source_diff_reference == "git:base..proposal"


def test_removed_identity_view_and_reviewed_rename_are_explicit(tmp_path: Path) -> None:
    current = _artifact(tmp_path / "current", extra_view=True)
    unreviewed = _artifact(
        tmp_path / "unreviewed", element_id="element.system.renamed"
    )
    unreviewed_diff = compute_c4_semantic_diff(
        current, unreviewed, source_diff_reference="git:base..unreviewed"
    )
    unreviewed_changes = {
        item.semantic_id: item.state for item in unreviewed_diff.identities
    }
    assert unreviewed_changes["element.system"] == "removed"
    assert unreviewed_changes["element.system.renamed"] == "added"

    proposed = _artifact(
        tmp_path / "proposed",
        element_id="element.system.renamed",
        include_container=False,
        renames=(
            C4Rename("element.system", "element.system.renamed", "architecture-review"),
        ),
    )

    diff = compute_c4_semantic_diff(
        current, proposed, source_diff_reference="git:base..proposal"
    )

    changes = {item.semantic_id: item for item in diff.identities}
    assert changes["element.system.renamed"].previous_semantic_id == "element.system"
    assert changes["element.system.renamed"].state == "unchanged"
    assert changes["element.container"].state == "removed"
    assert {view.key: view.state for view in diff.views} == {
        "added": "removed_view",
        "main": "changed",
    }


def test_first_empty_and_render_error_states_are_consumable(tmp_path: Path) -> None:
    proposed = _artifact(tmp_path / "proposed")
    first = compute_c4_semantic_diff(
        None, proposed, source_diff_reference="git:empty..proposal"
    )
    assert first.state == "first_model"
    assert first.views[0].state == "first_model"

    empty_render = C4RenderArtifact(status="empty", closure_digest="empty")
    empty = C4SemanticModelArtifact("proposal:empty", empty_render, proposed.contract)
    baseline_diff = compute_c4_semantic_diff(
        empty, proposed, source_diff_reference="git:empty..proposal"
    )
    assert baseline_diff.state == "empty_baseline"
    assert baseline_diff.views[0].state == "empty_baseline"

    empty_diff = compute_c4_semantic_diff(
        proposed, empty, source_diff_reference="git:proposal..empty"
    )
    assert empty_diff.state == "empty_proposal"
    assert empty_diff.views[0].state == "empty_proposal"

    failed_render = C4RenderArtifact(
        status="render_error",
        closure_digest="failed",
        view_keys=("main",),
        failure=C4RenderFailure("invalid_artifact", "export", "broken JSON"),
    )
    failed = C4SemanticModelArtifact("proposal:failed", failed_render, proposed.contract)
    error_diff = compute_c4_semantic_diff(
        proposed, failed, source_diff_reference="git:proposal..failed"
    )
    assert error_diff.state == "render_error"
    assert error_diff.views[0].state == "render_error"
    assert "broken JSON" in (error_diff.error or "")


def test_contract_render_identity_mismatch_is_a_visible_error(tmp_path: Path) -> None:
    current = _artifact(tmp_path / "current")
    proposed = _artifact(tmp_path / "proposed", omit_semantic_id="relationship.uses")

    diff = compute_c4_semantic_diff(
        current, proposed, source_diff_reference="git:base..proposal"
    )

    assert diff.state == "render_error"
    assert "identity mismatch" in (diff.error or "")
    assert diff.changed_view_keys == ("main",)


def _artifact(
    directory: Path,
    *,
    export_offset: int = 0,
    x: int = 10,
    description: str = "System",
    container_parent: bool = True,
    view_elements: tuple[str, ...] = ("element.system",),
    extra_view: bool = False,
    element_id: str = "element.system",
    include_container: bool = True,
    renames: tuple[C4Rename, ...] = (),
    omit_semantic_id: str | None = None,
) -> C4SemanticModelArtifact:
    directory.mkdir(parents=True)
    ids = {
        element_id: str(1 + export_offset),
        "element.container": str(2 + export_offset),
        "relationship.uses": str(3 + export_offset),
    }
    container = _element(ids["element.container"], "Container", "element.container")
    system = _element(ids[element_id], description, element_id)
    if include_container and container_parent:
        system["containers"] = [container]
    relationship = {
        "id": ids["relationship.uses"],
        "sourceId": ids[element_id],
        "destinationId": ids["element.container"],
        "description": "Uses",
        "properties": {
            "cascade.semanticId": "relationship.uses",
            "structurizr.dsl.identifier": "uses",
        },
        "tags": "Relationship",
    }
    if omit_semantic_id == "relationship.uses":
        relationship["properties"] = {"structurizr.dsl.identifier": "uses"}
    system["relationships"] = [relationship] if include_container else []
    people = (
        []
        if include_container and container_parent
        else ([container] if include_container else [])
    )
    semantic_to_export = ids

    def view(key: str, members: tuple[str, ...]) -> dict[str, object]:
        return {
            "key": key,
            "name": key.title(),
            "order": 99,
            "automaticLayout": {"rankDirection": "LeftRight"},
            "elements": [
                {"id": semantic_to_export[item], "x": x, "y": x * 2}
                for item in members
                if item in semantic_to_export
            ],
            "relationships": (
                [{"id": ids["relationship.uses"]}] if include_container else []
            ),
        }

    views = [
        view(
            "main",
            tuple(
                element_id if item == "element.system" else item
                for item in view_elements
            ),
        )
    ]
    if extra_view:
        views.append(view("added", (element_id,)))
    payload = {
        "id": export_offset,
        "model": {"softwareSystems": [system], "people": people},
        "views": {"systemLandscapeViews": views},
    }
    workspace = directory / "workspace.json"
    workspace.write_text(json.dumps(payload), encoding="utf-8")

    elements = [C4Element("system", element_id, Path("model.dsl"))]
    if include_container:
        elements.append(C4Element("container", "element.container", Path("model.dsl")))
    relationships = (
        (
            C4Relationship(
                "uses",
                "relationship.uses",
                "system",
                "container",
                Path("model.dsl"),
            ),
        )
        if include_container
        else ()
    )
    contract = C4WorkspaceContract(
        root=directory,
        source=Path("workspace.dsl"),
        owner="test",
        fragment_owners={Path("model.dsl"): "test", Path("views.dsl"): "test"},
        elements=tuple(elements),
        relationships=relationships,
        views=tuple(C4View(item["key"], Path("views.dsl")) for item in views),
        renames=renames,
    )
    render = C4RenderArtifact(
        status="ready",
        closure_digest=directory.name,
        semantic_workspace=workspace,
        view_keys=tuple(sorted(item["key"] for item in views)),
    )
    return C4SemanticModelArtifact(f"artifact:{directory.name}", render, contract)


def _element(export_id: str, description: str, semantic_id: str) -> dict[str, object]:
    return {
        "id": export_id,
        "name": "Same label",
        "description": description,
        "properties": {
            "cascade.semanticId": semantic_id,
            "structurizr.dsl.identifier": semantic_id.replace(".", "_"),
        },
        "tags": "Element",
    }
