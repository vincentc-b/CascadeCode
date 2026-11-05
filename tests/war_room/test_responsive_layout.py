"""Browser-level regression coverage for the responsive War Room shell."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _ROOT / "cascade" / "war_room" / "templates" / "war_room.html"
_STYLES = _ROOT / "cascade" / "war_room" / "static" / "war_room.css"


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

    assert 'grid-template-areas: "context board utilities"' in css
    assert "minmax(28rem, 42rem)" in css
    for region in (".room-panels", ".board-panel", ".side-panels"):
        block = css.split(region, 1)[1].split("}", 1)[0]
        assert "min-width: 0" in block
    narrow = css.split("@media (max-width: 1240px)", 1)[1]
    assert '"board"\n      "context"\n      "utilities"' in narrow
    assert 'id="room-panels"' in template
    assert 'aria-label="Context"' in template
    assert 'aria-label="Utilities"' in template

    render_board = script.split("function renderBoard(view)", 1)[1].split(
        "function wireCompletedCollapseControls", 1
    )[0]
    assert "el.board.innerHTML" not in render_board
    assert 'colEl.innerHTML = ""' in render_board


def _box(page, selector: str) -> dict[str, float]:
    box = page.locator(selector).bounding_box()
    assert box is not None
    return box


def _load_shell(page) -> None:
    html = _TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("${boss_panel_markup}", "")
    html = html.replace("${epic_graph_id}", "epic_001")
    html = html.replace("${branch_label_example}", "task_001")
    page.set_content(html, wait_until="domcontentloaded")
    page.add_style_tag(path=str(_STYLES))
    page.locator('[data-tier="features"] [data-column="1_backlog"]').evaluate(
        """column => {
          column.innerHTML = '<div class="board-row"><div class="board-row-title">Short feature title</div></div>';
        }"""
    )


def test_wide_shell_is_centered_and_board_width_survives_poll_rerender(
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
    assert 650 <= board_before["width"] <= 680

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
