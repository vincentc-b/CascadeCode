"""Full-model browser receipt for Task 051-004-004.

Run with ``PYTHONPATH=. python <this-file>`` from a clean task checkout after
the current architecture has been rendered once.  The script installs nothing,
uses production architecture routes, and writes its receipt below ``.cascade``.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from cascade.board.context import set_project_context
from cascade.war_room.server import serve
from cascade.workspace import ProjectContext
from cascade.workspace.integration_worktree import locate_trunk
from cascade.workspace.types import RepositoryContext


ROOT = Path.cwd()
PATHS = (
    ("war-room", "dashboard", "cascade-dashboard-code", "element.code.dashboard.review-projection", "feature_review_views"),
    ("war-room", "war-room-http", "cascade-war-room-http-code", "element.code.http.review-repair", "handle_post_review_repair"),
    ("supervisor", "feature-team", "cascade-feature-code", "element.code.feature.open-review-repair", "admit_open_review_repair"),
    ("supervisor", "feature-team", "cascade-feature-code", "element.code.feature.latest-open-review-repair", "latest_feature_repair_records"),
    ("supervisor", "task-team", "cascade-task-code", "element.code.task.upstream-review-fence", "record_upstream_review_observation"),
    ("supervisor", "epic-team", "cascade-epic-code", "element.code.epic.review-repair-request", "request_feature_review_repair"),
    ("supervisor", "watchdog", "cascade-watchdog-code", "element.code.watchdog.actionable-review-health", "_route_actionable_review_health"),
    ("supervisor", "watchdog", "cascade-watchdog-code", "element.code.watchdog.review-evidence-record", "record_feature_review_evidence"),
    ("supervisor", "boss", "cascade-boss-code", "element.code.boss.repair-postcheck-gate", "_current_open_review_postcheck_matches"),
    ("supervisor", "workspace", "cascade-workspace-code", "element.code.workspace.retained-feature-delivery", "_retained_feature_delivery"),
)


def main() -> None:
    canonical = ProjectContext.colocated(locate_trunk(ROOT))
    repository = RepositoryContext(
        root=ROOT, repository_key=canonical.target.repository_key
    )
    set_project_context(ProjectContext(repository, repository))
    server = serve(root=ROOT, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    result: dict[str, object] = {"paths": [], "http_errors": []}
    started = time.monotonic()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.set_default_timeout(30_000)
            page.on(
                "response",
                lambda response: result["http_errors"].append(
                    {"url": response.url, "status": response.status}
                )
                if "/api/architecture/" in response.url and response.status >= 400
                else None,
            )
            page.route(
                "**/api/**",
                lambda route: route.continue_()
                if "/api/architecture/" in route.request.url
                else route.fulfill(
                    status=200, content_type="application/json", body="{}"
                ),
            )
            page.goto(base + "/?tab=architecture", wait_until="domcontentloaded")
            page.locator("#architecture-ready:not([hidden])").wait_for(timeout=210_000)
            page.locator("#architecture-viewer .semantic-c4-svg").wait_for()
            result["ready_seconds"] = time.monotonic() - started
            ledger = ROOT / ".cascade" / "c4-render-operations.json"
            result["render_operations_before"] = len(
                json.loads(ledger.read_text())["operations"]
            )
            view = page.locator("#architecture-view")

            def select_view(key: str) -> None:
                options = view.locator("option")
                index = next(
                    index
                    for index, text in enumerate(options.all_text_contents())
                    if key in text
                )
                view.select_option(index=index)
                page.locator("#architecture-viewer .semantic-c4-svg").wait_for()

            def target(semantic_id: str) -> None:
                page.locator(f'[aria-label="element {semantic_id}"]').click()

            for container, component, code_view, node, symbol in PATHS:
                tick = time.monotonic()
                select_view("cascade-context")
                target("element.system.cascade")
                assert "cascade-containers" in view.input_value()
                target("element.container." + container)
                component_view = f"cascade-{container}-components"
                if component_view not in view.input_value():
                    page.locator("#architecture-drill-choices button").filter(
                        has_text=component_view
                    ).click()
                target("element.component." + component)
                if code_view not in view.input_value():
                    page.locator("#architecture-drill-choices button").filter(
                        has_text=code_view
                    ).click()
                assert code_view in view.input_value(), view.input_value()
                target(node)
                deep_link = page.url
                assert f"target={node}" in deep_link and f"view={code_view}" in deep_link
                page.reload(wait_until="domcontentloaded")
                page.locator("#architecture-ready:not([hidden])").wait_for()
                assert (
                    page.locator(f'[aria-label="element {node}"]').get_attribute(
                        "aria-pressed"
                    )
                    == "true"
                )
                page.locator(
                    "#architecture-target-detail button", has_text="Open pinned source"
                ).click()
                preview = page.locator("#architecture-document-preview-body")
                preview.filter(has_text=symbol).wait_for()
                assert symbol in preview.inner_text()
                page.locator("#architecture-back").click()
                assert "components" in view.input_value()
                result["paths"].append(
                    {
                        "component": component,
                        "view": code_view,
                        "node": node,
                        "symbol": symbol,
                        "deep_link_restored": True,
                        "pinned_source_opened": True,
                        "level_up": True,
                        "elapsed_seconds": time.monotonic() - tick,
                    }
                )

            result["render_operations_after"] = len(
                json.loads(ledger.read_text())["operations"]
            )
            assert result["render_operations_after"] == result["render_operations_before"]
            assert not result["http_errors"], result["http_errors"]
            result["provenance"] = page.locator(
                "#architecture-provenance-list"
            ).inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        set_project_context(None)
        result["total_seconds"] = time.monotonic() - started
        receipt = ROOT / ".cascade" / "task051004004-browser.json"
        receipt.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
