"""Browser-level regression coverage for the responsive War Room shell."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _ROOT / "cascade" / "war_room" / "templates" / "war_room.html"
_STYLES = _ROOT / "cascade" / "war_room" / "static" / "war_room.css"
_RESIZING = _ROOT / "cascade" / "war_room" / "static" / "panel_resizing.js"
_PRIORITY_UI = _ROOT / "cascade" / "war_room" / "static" / "backlog_priority_ui.js"
_RESIZING_CASES = Path(__file__).with_name("panel_resizing_cases.mjs")


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:
            instance = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium is unavailable: {exc}")
        try:
            yield instance
        finally:
            instance.close()


def test_shell_declares_content_independent_wide_and_narrow_tracks():
    """Keep a fast contract check when a browser binary is unavailable."""
    css = _STYLES.read_text(encoding="utf-8")
    template = _TEMPLATE.read_text(encoding="utf-8")
    script = (_ROOT / "cascade" / "war_room" / "static" / "war_room.js").read_text(
        encoding="utf-8"
    )

    assert (
        'grid-template-areas: "context context-resizer board utilities-resizer utilities"'
        in css
    )
    assert "minmax(28rem, 1fr)" in css
    for region in (".room-panels", ".board-panel", ".side-panels"):
        block = css.split(region, 1)[1].split("}", 1)[0]
        assert "min-width: 0" in block
    narrow = css.split("@media (max-width: 1240px)", 1)[1]
    assert '"board"\n      "context"\n      "utilities"' in narrow
    assert 'id="room-panels"' in template
    assert 'aria-label="Context"' in template
    assert 'aria-label="Utilities"' in template
    assert 'aria-label="Resize context panel"' in template
    assert 'aria-label="Resize utilities panel"' in template
    assert 'id="btn-reset-panel-sizes"' in template

    render_board = script.split("function renderBoard(view)", 1)[1].split(
        "function wireCompletedCollapseControls", 1
    )[0]
    assert "el.board.innerHTML" not in render_board
    assert 'colEl.innerHTML = ""' in render_board


def test_panel_resizing_interaction_cases():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for panel resizing interaction cases")
    result = subprocess.run(
        [node, str(_RESIZING_CASES)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def _box(page, selector: str) -> dict[str, float]:
    box = page.locator(selector).bounding_box()
    assert box is not None
    return box


def _load_shell(page) -> None:
    html = _TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("${boss_panel_markup}", "")
    html = html.replace("${epic_graph_id}", "epic_001")
    html = html.replace("${branch_label_example}", "task_001")
    # The shell tests load the interaction scripts explicitly when needed.
    # Removing server-relative assets prevents about:blank fetches from
    # delaying DOMContentLoaded in browser-only test environments.
    html = re.sub(r'\s*<script src="[^"]+"></script>', "", html)
    page.set_content(html, wait_until="domcontentloaded")
    page.add_style_tag(path=str(_STYLES))
    page.locator('[data-tier="features"] [data-column="1_backlog"]').evaluate(
        """column => {
          column.innerHTML = '<div class="board-row"><div class="board-row-title">Short feature title</div></div>';
        }"""
    )


def _enable_resizing(page, stored_value: str | None = None) -> None:
    page.evaluate(
        """storedValue => {
          const values = new Map();
          if (storedValue !== null) {
            values.set('cascade-war-room-panel-sizes-v1', storedValue);
          }
          window.__panelStorage = {
            getItem(key) { return values.has(key) ? values.get(key) : null; },
            setItem(key, value) { values.set(key, String(value)); },
            removeItem(key) { values.delete(key); },
          };
          Object.defineProperty(window, 'localStorage', {
            configurable: true,
            value: window.__panelStorage,
          });
        }""",
        stored_value,
    )
    page.add_script_tag(path=str(_RESIZING))


def test_wide_shell_fills_viewport_and_board_width_survives_poll_rerender(
    browser,
):
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    _load_shell(page)
    page.locator(".board-row-title", has_text="Short feature title").wait_for()

    context = _box(page, "#room-panels")
    board_before = _box(page, "#war-room-board")
    utilities = _box(page, ".side-panels")

    assert context["x"] < board_before["x"] < utilities["x"]
    assert abs((board_before["x"] + board_before["width"] / 2) - 800) <= 1
    assert board_before["width"] >= 850
    assert utilities["x"] + utilities["width"] >= 1570

    # renderBoard replaces each column's descendants after a poll. A long
    # unbroken title catches intrinsic-grid sizing regressions that previously
    # moved the board boundaries when that fresh content arrived.
    long_title = "Polled-" + ("content" * 45)
    page.locator('[data-tier="features"] [data-column="1_backlog"]').evaluate(
        """(column, title) => {
          column.innerHTML = '';
          const row = document.createElement('div');
          row.className = 'board-row';
          const heading = document.createElement('div');
          heading.className = 'board-row-title';
          heading.textContent = title;
          row.appendChild(heading);
          column.appendChild(row);
        }""",
        long_title,
    )

    board_after = _box(page, "#war-room-board")
    assert board_after["x"] == pytest.approx(board_before["x"], abs=0.5)
    assert board_after["width"] == pytest.approx(board_before["width"], abs=0.5)
    assert page.evaluate("document.documentElement.scrollWidth") <= 1600


def test_narrow_shell_stacks_board_context_and_utilities_without_overflow(
    browser,
):
    page = browser.new_page(viewport={"width": 720, "height": 1000})
    _load_shell(page)
    page.locator(".board-row-title", has_text="Short feature title").wait_for()

    board = _box(page, "#war-room-board")
    context = _box(page, "#room-panels")
    utilities = _box(page, ".side-panels")

    assert board["y"] < context["y"] < utilities["y"]
    assert board["x"] == pytest.approx(context["x"], abs=0.5)
    assert board["width"] == pytest.approx(context["width"], abs=0.5)
    assert board["width"] == pytest.approx(utilities["width"], abs=0.5)
    assert page.evaluate("document.documentElement.scrollWidth") <= 720

    # Core controls from all three regions remain present and reachable.
    assert page.locator("#btn-create-brief").is_visible()
    assert page.locator("#chat-body").is_visible()
    assert page.locator("#btn-refresh-open-reviews").is_visible()


def test_resize_persist_restore_and_reset_flow_is_bounded_and_accessible(browser):
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    _load_shell(page)
    _enable_resizing(page, '{"version":1,"context":"huge","utilities":9999}')

    context_handle = page.locator("#context-panel-resizer")
    utilities_handle = page.locator("#utilities-panel-resizer")
    assert context_handle.get_attribute("role") == "separator"
    assert context_handle.get_attribute("aria-orientation") == "vertical"
    assert _box(page, "#room-panels")["width"] == pytest.approx(320, abs=0.5)
    assert page.evaluate(
        "localStorage.getItem('cascade-war-room-panel-sizes-v1')"
    ) is None

    # Keyboard resizing can use space beyond the old fixed panel cap.
    context_handle.focus()
    context_handle.press("End")
    context_width = _box(page, "#room-panels")["width"]
    assert context_width > 384
    assert context_handle.get_attribute("aria-valuenow") == str(round(context_width))

    # Pointer resizing in the opposite direction clamps the utilities panel.
    context_handle.press("Home")
    context_width = _box(page, "#room-panels")["width"]
    handle_box = _box(page, "#utilities-panel-resizer")
    page.mouse.move(handle_box["x"] + handle_box["width"] / 2, handle_box["y"] + 20)
    page.mouse.down()
    page.mouse.move(0, handle_box["y"] + 20)
    page.mouse.up()
    utilities_width = _box(page, ".side-panels")["width"]
    assert utilities_width > 420

    saved = page.evaluate(
        "localStorage.getItem('cascade-war-room-panel-sizes-v1')"
    )
    assert saved is not None
    assert page.evaluate("value => JSON.parse(value)", saved) == {
        "version": 1,
        "context": round(context_width),
        "utilities": round(utilities_width),
    }

    # A fresh document restores the validated values before any board polling.
    restored = browser.new_page(viewport={"width": 1600, "height": 1000})
    _load_shell(restored)
    _enable_resizing(restored, saved)
    assert _box(restored, "#room-panels")["width"] == pytest.approx(context_width, abs=0.5)
    assert _box(restored, ".side-panels")["width"] == pytest.approx(utilities_width, abs=0.5)

    restored.locator("#btn-reset-panel-sizes").click()
    assert _box(restored, "#room-panels")["width"] == pytest.approx(320, abs=0.5)
    assert _box(restored, ".side-panels")["width"] == pytest.approx(320, abs=0.5)
    assert restored.evaluate(
        "localStorage.getItem('cascade-war-room-panel-sizes-v1')"
    ) is None
    assert restored.locator("#panel-size-status").text_content() == (
        "Panel sizes reset to defaults"
    )


def test_backlog_feature_drag_handle_submits_reorder_in_browser(browser):
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    _load_shell(page)
    page.add_script_tag(path=str(_PRIORITY_UI))
    page.evaluate(
        """() => {
          const column = document.querySelector('[data-tier="features"] [data-column="1_backlog"]');
          column.replaceChildren();
          window.reorderRequests = [];
          const controller = BacklogPriorityUi.createController({
            document,
            board: document.getElementById('war-room-board'),
            apiPost(path, payload) {
              window.reorderRequests.push({path, payload});
              return Promise.resolve({body: {feature_ids: payload.feature_ids, token: 'accepted'}});
            },
            setStatus() {},
            rerender() {},
          });
          controller.syncBoard({backlog_feature_priorities: {
            epic_a: {feature_ids: ['feat_1', 'feat_2', 'feat_3'], token: 'initial'},
          }});
          for (const id of ['feat_1', 'feat_2', 'feat_3']) {
            const row = document.createElement('div');
            row.className = 'board-row';
            row.dataset.id = id;
            const title = document.createElement('div');
            title.className = 'board-row-title';
            title.textContent = id;
            row.appendChild(title);
            controller.decorateRow(row, {id, parent: 'epic_a'});
            column.appendChild(row);
          }
        }"""
    )
    source = page.locator('[data-id="feat_1"] .backlog-drag-hint')
    target = page.locator('[data-id="feat_3"]')
    assert source.is_visible()
    source.drag_to(target)
    assert page.evaluate("window.reorderRequests") == [
        {
            "path": "/api/reorder_backlog_features",
            "payload": {
                "epic_id": "epic_a",
                "feature_ids": ["feat_2", "feat_1", "feat_3"],
                "expected_token": "initial",
            },
        }
    ]
