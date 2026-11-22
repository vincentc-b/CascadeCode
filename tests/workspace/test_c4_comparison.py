"""Single comparison graphs retain deleted context and honest connection changes."""

import pytest
from cascade.workspace.c4_comparison import comparison_targets, comparison_source
from cascade.workspace import C4ArtifactRenderer, C4RenderSettings


def node(identity, label=None, state="unchanged"):
    return {
        "kind": "element",
        "semantic_id": identity,
        "label": label or identity,
        "state": state,
    }


def edge(identity, source, destination, state="unchanged"):
    return {
        "kind": "relationship",
        "semantic_id": identity,
        "source": source,
        "destination": destination,
        "label": "Calls",
        "state": state,
    }


def view():
    return {
        "key": "service",
        "level": "componentViews",
        "current": {
            "targets": [
                node("element.a", "Before"),
                node("element.b"),
                node("element.gone"),
                edge("relationship.call", "element.a", "element.b", "changed"),
            ]
        },
        "proposed": {
            "targets": [
                node("element.a", "After", "changed"),
                node("element.b"),
                node("element.new"),
                edge("relationship.call", "element.a", "element.new", "changed"),
            ]
        },
    }


def test_union_retains_removed_nodes_and_old_connection():
    rows = comparison_targets(view())
    by_id = {r["semantic_id"]: r for r in rows}
    assert by_id["element.gone"]["state"] == "removed"
    assert by_id["element.new"]["state"] == "added"
    assert by_id["element.a"]["state"] == "changed"
    assert by_id["element.a"]["before"]["label"] == "Before"
    assert by_id["element.a"]["after"]["label"] == "After"
    edges = [r for r in rows if r["kind"] == "relationship"]
    assert {(r["destination"], r["state"]) for r in edges} == {
        ("element.b", "removed"),
        ("element.new", "added"),
    }
    assert len({r["semantic_id"] for r in rows}) == len(rows)


def test_reviewed_rename_remains_one_changed_node():
    source = {
        "current": {"targets": [node("element.old", state="changed")]},
        "proposed": {"targets": [node("element.new", state="changed")]},
    }
    rows = comparison_targets(source, {"element.old": "element.new"})
    assert len(rows) == 1
    assert rows[0]["state"] == "changed"
    assert rows[0]["before"]["semantic_id"] == "element.old"


def test_comparison_render_binds_union_and_reuses_cache(tmp_path):
    source = view()
    source["combined_targets"] = comparison_targets(source)
    inputs = tmp_path / "input"
    inputs.mkdir()
    removed_view = {
        "key": "old-scope",
        "level": "componentViews",
        "current": source["current"],
        "proposed": None,
    }
    removed_view["combined_targets"] = comparison_targets(removed_view)
    closure = comparison_source(
        [source, removed_view],
        inputs,
        owner="epic_047",
        evidence="pair:a:b",
        repository_key="repo",
    )
    renderer = C4ArtifactRenderer(tmp_path / "cache")
    result = renderer.submit(closure).wait(
        timeout=C4RenderSettings().timeout_seconds + 5
    )
    assert result.status == "ready", result
    import json

    bindings = json.loads(result.binding_manifest.read_text())
    assert {t["semantic_id"] for t in bindings["views"][0]["targets"]} == {
        identity for identity in source["combined_bindings"]
    }
    assert {t["semantic_id"] for t in bindings["views"][1]["targets"]} == set(
        removed_view["combined_bindings"]
    )
    assert set(source["combined_bindings"]).isdisjoint(
        removed_view["combined_bindings"]
    )
    assert renderer.submit(closure).wait(timeout=5).cache_hit


def test_scheduler_serves_one_validated_combined_svg(tmp_path):
    from cascade.workspace.c4_comparison import attach_comparison
    from cascade.workspace.c4_scheduler import (
        C4RenderScheduler,
        C4ScheduledRenderOperation,
    )

    source = view()
    for side in ("current", "proposed"):
        source[side].update(repository_key="repo", revision=side)
    import copy

    context = copy.deepcopy(source)
    context.update(key="context", level="systemContextViews")
    context["proposed"]["targets"][0]["drill_choices"] = [{"view_key": "deeper"}]
    payload = {
        "views": [source, context],
        "snapshot_ids": {"current": "a", "proposed": "b"},
        "owner_work_id": "epic_047",
        "state": "ready",
    }
    with C4RenderScheduler(tmp_path) as scheduler:
        attach_comparison(payload, scheduler)
        operation = payload["comparison_render_operation_id"]
        result = C4ScheduledRenderOperation(scheduler, operation).wait(timeout=185)
        assert result.status == "ready", result
        attach_comparison(payload, scheduler)
        assert payload["comparison_render_operation_id"] == operation
        assert source["combined"]["svg"].startswith("<")
        assert "element.gone" in source["combined"]["svg"]
        assert "element.new" in source["combined"]["svg"]
        assert source["combined"]["targets"] == source["combined_targets"]
        assert context["combined"]["svg"] == source["combined"]["svg"]
        assert context["combined"]["targets"] != source["combined"]["targets"]


def test_missing_endpoint_fails_instead_of_hiding_relationship(tmp_path):
    source = {
        "key": "broken",
        "level": "containerViews",
        "combined_targets": [
            {
                **edge("relationship.edge", "element.missing", "element.also-missing"),
                "source_side": "proposed",
            }
        ],
    }
    with pytest.raises(ValueError, match="unavailable endpoint"):
        comparison_source(
            [source], tmp_path, owner="epic_047", evidence="pair", repository_key="repo"
        )


def test_oversized_comparison_source_fails_explicitly(tmp_path):
    source = {
        "key": "large",
        "level": "containerViews",
        "combined_targets": [
            {
                **node("element.large", "x" * (2 * 1024 * 1024)),
                "source_side": "proposed",
            }
        ],
    }
    with pytest.raises(ValueError, match="2 MiB"):
        comparison_source(
            [source], tmp_path, owner="epic_047", evidence="pair", repository_key="repo"
        )


def test_pending_and_failed_renders_do_not_publish_partial_diagrams():
    from types import SimpleNamespace
    from cascade.workspace.c4_comparison import attach_comparison

    class Scheduler:
        status = "running"

        def admit(self, *args, **kwargs):
            return SimpleNamespace(
                operation_id="operation",
                snapshot=lambda: SimpleNamespace(
                    status=self.status,
                    failure=SimpleNamespace(message="render stopped"),
                ),
            )

    scheduler = Scheduler()
    source = view()
    for side in ("current", "proposed"):
        source[side]["repository_key"] = "repo"
    payload = {
        "views": [source],
        "owner_work_id": "epic_047",
        "snapshot_ids": {"current": "a", "proposed": "b"},
    }
    attach_comparison(payload, scheduler)
    assert payload["state"] == "pending"
    assert "combined" not in source
    scheduler.status = "failed"
    attach_comparison(payload, scheduler)
    assert payload["state"] == "render_failed"
    assert "render stopped" in payload["summary"]
    assert "combined" not in source


def test_layout_sharing_requires_identical_displayed_graph(tmp_path):
    import copy

    original = view()
    original["combined_targets"] = comparison_targets(original)
    same = copy.deepcopy(original)
    same.update(key="context", level="systemContextViews")
    same["combined_targets"].reverse()
    changed = copy.deepcopy(original)
    changed["key"] = "different-label"
    changed["combined_targets"][0]["label"] = "Different label"
    comparison_source(
        [original, same, changed],
        tmp_path,
        owner="epic_047",
        evidence="pair",
        repository_key="repo",
    )
    assert same["combined_render_key"] == original["combined_render_key"]
    assert same["combined_bindings"] == original["combined_bindings"]
    assert changed["combined_render_key"] != original["combined_render_key"]
    assert set(changed["combined_bindings"]).isdisjoint(original["combined_bindings"])
