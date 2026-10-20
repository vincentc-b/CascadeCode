"""Plan viewer HTML route (task_056)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.comments import section_slug

from dataclasses import replace

from cascade.board.store import read_doc, write_doc
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo

_PLAN_RENDER_APPENDIX = """

## Fixture appendix

| Key | Value |
|-----|-------|
| tier | feature |

```mermaid
flowchart TD
  A[Start] --> B[End]
```

Link: [feat_012](../../features/1_backlog/feat_012_plan_viewer.md).
"""

_STATIC_VENDOR = (
    Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "vendor"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_html(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()
        headers = dict(resp.headers)
        return resp.status, raw.decode(), headers


def _get_html_expect_error(url: str) -> tuple[int, str]:
    try:
        _get_html(url)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    raise AssertionError("expected HTTP error")


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_plan_known_doc(war_room_server):
    base = war_room_server
    status, html, headers = _get_html(f"{base}/plan/epic_001")
    assert status == HTTPStatus.OK
    assert "text/html" in headers.get("Content-type", headers.get("Content-Type", ""))
    assert 'data-work-id="epic_001"' in html
    assert "Back to War Room" in html
    assert "/static/vendor/marked.min.js" in html
    assert 'src="/static/vendor/mermaid.min.js"' not in html
    assert "/static/plan_viewer.js" in html
    assert "Timed out after 10s" in html
    assert "load-deadline-banner" in html
    _status, plan_js, _headers = _get_html(f"{base}/static/plan_viewer.js")
    assert "/static/vendor/mermaid.min.js" in plan_js
    assert "Timed out after 10s" in plan_js
    assert "PAGE_LOAD_MS = 10000" in plan_js
    assert 'id="plan-meta-parent-rev-note"' in html
    assert 'id="plan-comments"' in html
    assert "setInterval" not in plan_js
    assert 'tier === "task"' in plan_js
    assert "data-src-line" in plan_js
    assert "data-comment-id" in plan_js
    assert "plan-comment-section" not in html
    assert "sectionSlug" in plan_js
    assert "plan-gutter-add" in plan_js


def test_get_plan_task_tier_hides_comment_panel(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(root, id="task_001", title="Sample task", tier="task", parent="epic_001")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, html, _headers = _get_html(f"{base}/plan/task_001")
        assert status == HTTPStatus.OK
        assert 'data-work-id="task_001"' in html
        assert 'id="plan-comments"' in html
        _status, plan_js, _headers = _get_html(f"{base}/static/plan_viewer.js")
        assert "initPlanComments(workId, meta.tier," in plan_js
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_plan_markdown_fixture_doc(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(root, id="feat_012", title="Plan viewer", tier="feature", parent="epic_001")
    doc = read_doc("feat_012", root=root)
    write_doc(replace(doc, body=doc.body + _PLAN_RENDER_APPENDIX), root=root)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, html, _headers = _get_html(f"{base}/plan/feat_012")
        assert status == HTTPStatus.OK
        assert 'data-work-id="feat_012"' in html
        assert "/static/vendor/marked.min.js" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_plan_viewer_vendor_files_on_disk():
    marked = _STATIC_VENDOR / "marked.min.js"
    mermaid = _STATIC_VENDOR / "mermaid.min.js"
    assert marked.is_file()
    assert mermaid.is_file()


def test_get_plan_empty_id(war_room_server):
    base = war_room_server
    code, html = _get_html_expect_error(f"{base}/plan/")
    assert code == HTTPStatus.NOT_FOUND
    assert "Back to War Room" in html


def test_get_plan_unknown_doc(war_room_server):
    base = war_room_server
    code, html = _get_html_expect_error(f"{base}/plan/not_a_doc")
    assert code == HTTPStatus.NOT_FOUND
    assert "Back to War Room" in html


def test_get_plan_rejects_path_traversal(war_room_server):
    base = war_room_server
    code, _html = _get_html_expect_error(f"{base}/plan/epic_001/evil")
    assert code == HTTPStatus.NOT_FOUND


def test_section_slug_fixture_matches_python() -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "section_slug_vectors.json"
    pairs = json.loads(fixture.read_text(encoding="utf-8"))
    for heading, expected in pairs:
        assert section_slug(heading) == expected
        assert "_" not in expected


def test_static_plan_viewer_js(war_room_server):
    base = war_room_server
    status, _body, headers = _get_html(f"{base}/static/plan_viewer.js")
    assert status == HTTPStatus.OK
    assert "javascript" in headers.get("Content-type", headers.get("Content-Type", "")).lower()


def test_post_plan_method_not_allowed(war_room_server):
    base = war_room_server
    req = urllib.request.Request(
        f"{base}/plan/epic_001",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.METHOD_NOT_ALLOWED
