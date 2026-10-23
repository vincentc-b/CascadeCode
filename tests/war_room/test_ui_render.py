"""Server-rendered War Room home page (task_011)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.board.store import move_doc
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_html(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read().decode()
        return resp.status, raw, dict(resp.headers)


@pytest.fixture
def ui_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="epic_002", title="Second epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_002")
    add_doc(root, id="task_001", title="Work item", tier="task", parent="feat_001", status="active")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_home_is_server_rendered_html(ui_server):
    base, _root = ui_server
    for path in ("/", "/war-room"):
        status, html, headers = _get_html(f"{base}{path}")
        assert status == HTTPStatus.OK
        content_type = headers.get("Content-type", headers.get("Content-Type", ""))
        assert "text/html" in content_type
        assert 'id="war-room-board"' in html
        assert 'id="epic-war-room-chat"' in html
        assert 'id="toast-stream"' in html
        assert "Branch pattern: task/" in html
        assert 'id="branch-label-example">task_001<' in html
        assert "Timed out after 10s" in html
        assert "load-deadline-banner" in html


def test_default_epic_from_active_column(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'data-default-epic-graph-id="epic_002"' in html


def test_features_lens_empty_marker_in_html(ui_server):
    """Features tier exposes stable epic-lens empty copy (task_054)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert "data-board-features-lens-empty" in html
    assert "No epic is active or selected." in html


def test_completed_feature_awaiting_review_remains_in_active_lane(ui_server):
    base, root = ui_server
    move_doc("feat_001", "completed", root=root)
    state = root / ".cascade" / "reviews.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/pull/4",
                    "number": "4",
                    "forge": "github",
                    "source_branch": "feat/feat_001",
                    "target_branch": "epic/epic_002",
                    "draft": False,
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )

    _status, raw, _headers = _get_html(f"{base}/api/board")
    board = json.loads(raw)

    active = {item["id"]: item for item in board["features"]["2_active"]}
    completed = {item["id"] for item in board["features"]["3_completed"]}
    assert active["feat_001"]["review"] == {
        "state": "awaiting_review",
        "url": "https://github.example/pull/4",
        "number": "4",
        "draft": False,
    }
    assert "feat_001" not in completed


def test_tasks_lens_empty_marker_in_html(ui_server):
    """Tasks tier exposes stable feature-lens empty copy (task_055)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert "data-board-tasks-lens-empty" in html
    assert "Select a feature" in html


def test_completed_column_collapse_controls_in_html(ui_server):
    """Completed columns expose stable collapse markers (task_053)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert html.count("data-board-completed-collapse") == 3
    assert html.count("board-completed-collapse") >= 3
    for tier in ("epics", "features", "tasks"):
        assert f'data-board-tier="{tier}"' in html
    epics_tier = html.split('data-tier="epics"')[1].split('data-tier="features"')[0]
    assert "data-board-completed-history" in epics_tier
    assert 'aria-expanded="false"' in epics_tier
    assert "Expand" in epics_tier
    assert "board-column-completed-collapsed" in epics_tier
    assert html.index("/static/board_focus.js") < html.index("/static/open_reviews_pane.js")
    assert html.index("/static/open_reviews_pane.js") < html.index("/static/war_room.js")


def test_war_room_js_renders_completed_epics_history_link():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "renderCompletedEpicsHistory" in source
    assert "completed_epics_history" in source
    assert "board-action-link-unavailable" in source
    assert "Repository history link unavailable." in source


def test_war_room_js_renders_toast_body():
    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "toast.body" in source
    assert "toast.kind" in source
    assert "View plan" in source
    assert "/plan/" in source
    assert "Nothing in flight." in source
    assert "item.plan_approved" in source
    assert '"Approved"' in source
    assert 'approved.classList.add("approval-confirmed")' in source
    assert '"Awaiting review"' in source
    assert 'actionLink("Open review", item.review.url)' in source
    assert "EPIC_CLOSE_DEADLINE_MS = 60000" in source
    assert 'setStatus("Closing epic " + epicId + "…", false)' in source
    assert '"Epic close timed out after 60s"' in source


def test_war_room_js_explains_epic_close_comment_blockers():
    source = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    ).read_text(encoding="utf-8")

    assert 'body.reason === "open_human_comments"' in source
    assert 'body.plan_url || ("/plan/" + epicId + "#plan-comments")' in source


def test_task_execution_controls_and_board_polling_are_load_safe():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")

    assert 'status.setAttribute("aria-label", "Execution status: " + execution.label)' in source
    assert 'label: "Running"' in source
    assert 'label: "Blocked"' in source
    assert 'execution.health || execution.phase' in source
    assert 'label: "No signal"' in source
    assert '"Retry is available only when execution is blocked."' in source
    assert 'boardRefreshInFlight = apiGet("/api/board?_=" + Date.now())' in source
    assert source.count('apiGet("/api/board') == 1
    assert "return refreshBoard({ refreshRelated: false })" in source
    assert "setInterval(pollBoard" not in source
    assert "scheduleBoardPoll(boardPollDelayMs)" in source
    assert "Math.min(BOARD_POLL_MAX_MS, boardPollDelayMs * 2)" in source
    assert 'document.addEventListener("visibilitychange", handleVisibilityChange)' in source
    bootstrap = source[source.index("async function bootstrapWarRoom()") :]
    assert bootstrap.index("await Promise.allSettled([") < bootstrap.index(
        "scheduleBoardPoll(boardPollDelayMs)"
    )


def test_startup_does_not_duplicate_board_related_requests():
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")

    bootstrap = source[source.index("async function bootstrapWarRoom()") :]
    assert bootstrap.count("await refreshBoard();") == 1
    assert "refreshFlightReport().catch" not in bootstrap
    assert "refreshBossView();" not in bootstrap
    assert "pollChatSidecar()," not in bootstrap
    assert "relatedRefreshInFlight" in source


def test_task_execution_status_styles_include_healthy_and_blocked_states():
    css_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.css"
    )
    source = css_path.read_text(encoding="utf-8")

    assert ".task-execution-status-running" in source
    assert ".task-execution-status-healthy" in source
    assert ".task-execution-status-blocked" in source
    assert ".task-execution-status-stuck" in source


def test_epic_chat_compose_markup_and_enter_to_send(ui_server):
    """Epic chat exposes compose ids; Enter sends, Shift+Enter newline (war_room.js)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="chat-compose"' in html
    assert 'id="chat-body"' in html
    assert 'id="chat-send"' in html

    from pathlib import Path

    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "submitChatCompose" in source
    assert 'ev.key !== "Enter" || ev.shiftKey' in source
    assert "el.chatBody.value = \"\"" in source
    assert "const draft = body" in source


def test_war_room_html_loads_war_room_js(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert "/static/war_room.js" in html


def test_plan_page_includes_comment_compose(ui_server):
    base, _root = ui_server
    status, html, _headers = _get_html(f"{base}/plan/epic_001")
    assert status == HTTPStatus.OK
    assert 'id="plan-comment-body"' in html
    assert 'id="plan-comment-compose"' in html
    assert "Comment on the whole plan" in html
    assert 'id="plan-comment-compose" class="plan-comment-compose" hidden' not in html


def test_providers_pane_markup_in_html(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="providers-pane"' in html
    assert 'id="providers-list"' in html
    assert "Providers" in html


def test_brief_and_sync_controls_in_html(ui_server):
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="btn-create-brief"' in html
    assert 'id="btn-pull-main"' in html
    assert 'id="brief-form"' in html
    assert 'name="manager_model"' in html
    assert 'name="architect_model"' in html
    assert "Create merge request" in html


def test_open_reviews_pane_markup_in_html(ui_server):
    """Open merge requests panel exposes stable ids (feat_005 / task_012)."""
    base, _root = ui_server
    _status, html, _headers = _get_html(f"{base}/")
    assert 'id="open-reviews-pane"' in html
    assert 'id="open-reviews-list"' in html
    assert 'id="btn-refresh-open-reviews"' in html
    assert 'id="open-reviews-status"' in html
    assert "Open merge requests" in html


def test_open_reviews_js_queries_authoritative_api_only():
    static = Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static"
    pane_source = (static / "open_reviews_pane.js").read_text(encoding="utf-8")
    war_room_source = (static / "war_room.js").read_text(encoding="utf-8")
    assert 'apiGet("/api/open-reviews")' in pane_source
    assert "function refreshOpenReviews" in pane_source
    assert "function renderOpenReviews" in pane_source
    assert 'actionLink("Open review", review.url)' in pane_source
    assert "localStorage" not in pane_source
    assert "OpenReviewsPane" in war_room_source
    assert "createOpenReviewsPane" in war_room_source
