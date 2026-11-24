"""Real combined render through the one-canvas browser review flow."""

from pathlib import Path

import pytest

from cascade.workspace.c4_comparison import attach_comparison
from cascade.workspace.c4_scheduler import C4RenderScheduler, C4ScheduledRenderOperation


def test_single_canvas_preserves_removals_inspection_and_viewport(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")

    def node(identity, label, state="unchanged"):
        return {
            "kind": "element",
            "semantic_id": identity,
            "label": label,
            "state": state,
            "description": "Description for " + label,
            "type": "Component",
        }

    def side(revision, targets):
        return {
            "repository_key": "repo",
            "revision": revision,
            "targets": targets,
            "svg": "<svg/>",
        }

    before = [
        node("element.keep", "Before", "changed"),
        node("element.gone", "Retired"),
    ]
    after = [
        node("element.keep", "After", "changed"),
        node("element.new", "New service"),
    ]
    payload = {
        "state": "ready",
        "project_comparison": True,
        "owner_work_id": "epic_047",
        "semantic_threads": [],
        "snapshot_ids": {"current": "current-pin", "proposed": "proposal-pin"},
        "views": [
            {
                "key": "components",
                "level": "componentViews",
                "state": "changed",
                "current": side("current-pin", before),
                "proposed": side("proposal-pin", after),
            }
        ],
        "changed_views": [["components", "componentViews"]],
    }
    with C4RenderScheduler(tmp_path) as scheduler:
        attach_comparison(payload, scheduler)
        result = C4ScheduledRenderOperation(
            scheduler, payload["comparison_render_operation_id"]
        ).wait(timeout=185)
        assert result.status == "ready", result
        attach_comparison(payload, scheduler)
        assert "[c4:" not in payload["views"][0]["combined"]["svg"]
    assets = Path(__file__).parents[2] / "cascade/war_room/static"
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 900})
            page.set_content('<main><section id="review"></section></main>')
            page.add_style_tag(path=str(assets / "plan_viewer.css"))
            page.add_script_tag(path=str(assets / "plan_viewer.js"))
            page.evaluate(
                """payload => {
              window.payload = payload;
              window.review = PlanViewer.initPairedC4Review(structuredClone(payload), {
                document, host: document.getElementById('review'),
                refreshPayload:()=>structuredClone(payload)});
            }""",
                payload,
            )
            page.locator('[data-review-tab="c4"]').click()
            svg = page.locator(".semantic-c4-svg")
            svg.wait_for()
            assert svg.count() == 1
            for identity, state, color in [
                ("element.gone", "removed", "rgb(207, 34, 46)"),
                ("element.new", "added", "rgb(35, 134, 54)"),
                ("element.keep", "changed", "rgb(191, 135, 0)"),
            ]:
                hit = page.locator(f'[data-cascade-semantic-id="{identity}"]')
                assert hit.get_attribute("data-cascade-diff-state") == state
                assert (
                    hit.evaluate("(hit)=>getComputedStyle(hit).outlineColor") == color
                )
            fitted = svg.get_attribute("viewBox")
            page.get_by_role("button", name="Zoom in", exact=True).click()
            zoomed = svg.get_attribute("viewBox")
            assert zoomed != fitted
            page.locator('[aria-label="element element.keep"]').click()
            assert "Before" in page.locator(".c4-change-details").inner_text()
            assert "After" in page.locator(".c4-change-details").inner_text()
            assert svg.get_attribute("viewBox") == zoomed
            page.locator('[aria-label="element element.gone"]').click()
            assert (
                "Not present in this view."
                in page.locator(".c4-change-details").inner_text()
            )
            assert page.evaluate("review.selection().source_side") == "current"
            page.evaluate("review.refresh()")
            assert svg.count() == 1
            assert svg.get_attribute("viewBox") == zoomed
            page.get_by_role("button", name="Fit", exact=True).click()
            assert svg.get_attribute("viewBox") == fitted
            assert page.get_by_role("button", name="Link movement").count() == 0
            page.evaluate("review.stopRefresh()")
        finally:
            browser.close()


def test_expandable_comparison_click_navigates_and_list_inspects():
    playwright = pytest.importorskip("playwright.sync_api")
    identity = "element.system.cascade"
    target = {
        "kind": "element",
        "semantic_id": identity,
        "label": "Cascade",
        "state": "unchanged",
        "contains_changes": True,
        "drill_choices": [
            {
                "view_key": "context",
                "level": "systemContextViews",
                "scope_id": identity,
            },
            {"view_key": "containers", "level": "containerViews", "scope_id": identity},
        ],
    }
    side = {
        "repository_key": "repo",
        "revision": "pin",
        "targets": [target],
        "svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200">'
        f'<g data-cascade-semantic-id="{identity}" data-cascade-model-kind="element">'
        '<rect x="20" y="20" width="100" height="80"/><text x="30" y="60">Cascade</text>'
        "</g></svg>",
    }
    combined = {
        **side,
        "targets": [
            {
                **target,
                "selection_id": identity,
                "source_side": "proposed",
                "before": target,
                "after": target,
            }
        ],
    }
    payload = {
        "state": "ready",
        "project_comparison": True,
        "views": [
            {
                "key": key,
                "level": level,
                "current": side,
                "proposed": side,
                "combined": combined,
            }
            for key, level in [
                ("landscape", "systemLandscapeViews"),
                ("context", "systemContextViews"),
                ("containers", "containerViews"),
            ]
        ],
    }
    assets = Path(__file__).parents[2] / "cascade/war_room/static"
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('<section id="review"></section>')
            page.add_script_tag(path=str(assets / "plan_viewer.js"))
            page.evaluate(
                """payload => {
                window.review = PlanViewer.initPairedC4Review(payload, {
                    document, host: document.getElementById('review')});
            }""",
                payload,
            )
            page.locator('[data-review-tab="c4"]').click()
            select = page.locator(".paired-c4-view-select")
            assert select.input_value() == "context\0systemContextViews"
            assert page.locator(".paired-c4-up").is_disabled()
            page.locator("[data-cascade-semantic-id]").click()
            assert select.input_value() == "containers\0containerViews"
            page.locator(".paired-c4-up").click()
            assert select.input_value() == "context\0systemContextViews"
            assert page.locator(".paired-c4-up").is_disabled()
            page.locator(".semantic-c4-targets summary").click()
            page.locator(".semantic-c4-target-button").click()
            assert select.input_value() == "context\0systemContextViews"
            assert "Before" in page.locator(".c4-change-details").inner_text()
            page.locator("[data-cascade-semantic-id]").press("Enter")
            assert select.input_value() == "containers\0containerViews"
            select.select_option("landscape\0systemLandscapeViews")
            page.locator("[data-cascade-semantic-id]").click()
            assert select.input_value() == "context\0systemContextViews"
            assert page.locator(".paired-c4-up").is_disabled()
            page.evaluate("review.stopRefresh()")
        finally:
            browser.close()
