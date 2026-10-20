"""Server-rendered War Room home page (task_011)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http import HTTPStatus

import pytest

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
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
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
    assert html.index("/static/board_focus.js") < html.index("/static/war_room.js")


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
