"""War Room POST /api/comment and GET /api/comments/{doc_id} (task_078)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from http import HTTPStatus

import pytest

from cascade.war_room.server import serve
from cascade.workspace import (
    C4ReviewPayload,
    C4ReviewSide,
    C4ReviewTarget,
    C4ReviewView,
    build_semantic_thread_anchor,
)
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


@pytest.fixture
def war_room_server(tmp_path, monkeypatch):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Beta",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    monkeypatch.setattr(
        "cascade.war_room.architecture_routes.resolve_review_context",
        lambda _root, work_id: _review_payload(work_id),
    )
    add_doc(
        root,
        id="task_001",
        title="Alpha",
        tier="task",
        parent="feat_001",
        status="active",
    )
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_root_comment_slugifies_section_and_persists_optional_fields(war_room_server) -> None:
    base, _root, _server = war_room_server
    status, body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "section": "Memory layout",
            "body": "line bind note",
            "line_start": 2,
            "line_end": 4,
            "doc_sha": "deadbeef",
            "blocks": ["task_001"],
        },
    )
    assert status == HTTPStatus.ACCEPTED
    root_id = body["comment_id"]

    status, payload = _get(f"{base}/api/comments/feat_001")
    assert status == HTTPStatus.OK
    row = next(c for c in payload["comments"] if c["id"] == root_id)
    assert row["section"] == "memory-layout"
    assert row["line_start"] == 2
    assert row["line_end"] == 4
    assert row["doc_sha"] == "deadbeef"
    assert row["blocks"] == ["task_001"]


@pytest.mark.parametrize(
    ("kind", "target_key", "view_key", "level"),
    (
        ("requirement", "REQ-7", None, None),
        ("view", "context", "context", "systemContextViews"),
        ("element", "element.system", None, None),
        ("relationship", "relationship.calls", None, None),
    ),
)
def test_semantic_comment_api_preserves_typed_anchor(
    war_room_server, kind, target_key, view_key, level
) -> None:
    base, _root, _server = war_room_server
    anchor = build_semantic_thread_anchor(
        _review_payload("feat_001"), kind=kind, target_key=target_key,
        source_side="proposed", level=level,
    ).to_dict()
    status, body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "body": f"review {kind}",
            "blocking": kind == "relationship",
            "semantic_anchor": anchor,
        },
    )
    assert status == HTTPStatus.ACCEPTED

    _status, payload = _get(f"{base}/api/comments/feat_001")
    row = next(item for item in payload["comments"] if item["id"] == body["comment_id"])
    assert row["section"] == "semantic-review"
    assert row["semantic_anchor"] == anchor
    assert row["anchor"] is None
    assert row["line_start"] is None
    assert row["blocking"] is (kind == "relationship")
    assert row["freshness"] == "current"
    if kind == "requirement":
        assert row["semantic_anchor"]["repository_key"] == "plans"
        assert row["semantic_anchor"]["revision"] == "p" * 40
        assert row["semantic_anchor"]["source_path"] == "docs/feature.md"
        assert row["semantic_anchor"]["source_section"] == "REQ-7"


def test_semantic_comment_api_rejects_mixed_or_malformed_anchors(war_room_server) -> None:
    base, _root, _server = war_room_server
    malformed = {
        "version": 1,
        "kind": "element",
        "target_key": "element.system",
    }
    code, error = _post_expect_error(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "body": "bad", "semantic_anchor": malformed},
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "anchor" in error["error"]

    complete = {
        "version": 1,
        "kind": "element",
        "target_key": "element.system",
        "view_key": None,
        "level": None,
        "source_side": "current",
        "repository_key": "architecture-docs",
        "revision": "a" * 40,
        "review_unit_id": "architecture-review-exact",
        "reviewed_tuple_digest": "tuple-exact",
        "original_source_reference": "artifacts/current.svg",
        "original_diff_link": "/diff/model-a..model-b",
    }
    code, error = _post_expect_error(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "body": "mixed",
            "line_start": 3,
            "semantic_anchor": complete,
        },
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "document anchors" in error["error"]


def test_semantic_http_rejects_forged_and_stale_anchors(war_room_server) -> None:
    base, _root, _server = war_room_server
    anchor = build_semantic_thread_anchor(
        _review_payload("feat_001"), kind="element", target_key="element.system",
        source_side="proposed",
    ).to_dict()
    for forged in (
        {**anchor, "repository_key": "another-repository"},
        {**anchor, "reviewed_tuple_digest": "old-browser-tuple"},
        {**anchor, "target_key": "element.forged"},
    ):
        code, error = _post_expect_error(
            f"{base}/api/comment",
            {"doc_id": "feat_001", "body": "forged", "semantic_anchor": forged},
        )
        assert code == HTTPStatus.CONFLICT
        assert "semantic thread anchor" in error["error"] or "absent" in error["error"]

    requirement = build_semantic_thread_anchor(
        _review_payload("feat_001"), kind="requirement", target_key="REQ-7",
        source_side="proposed",
    ).to_dict()
    code, error = _post_expect_error(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "body": "forged requirement source",
            "semantic_anchor": {**requirement, "source_path": "docs/other.md"},
        },
    )
    assert code == HTTPStatus.CONFLICT
    assert "document source is not pinned" in error["error"]


def test_semantic_http_marks_a_previous_review_tuple_outdated(
    war_room_server, monkeypatch
) -> None:
    base, _root, _server = war_room_server
    original = _review_payload("feat_001")
    anchor = build_semantic_thread_anchor(
        original, kind="element", target_key="element.system",
        source_side="proposed",
    ).to_dict()
    _status, created = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "body": "old tuple", "semantic_anchor": anchor},
    )
    monkeypatch.setattr(
        "cascade.war_room.architecture_routes.resolve_review_context",
        lambda _root, _work_id: replace(
            original,
            review_unit_id="architecture-review-next",
            reviewed_tuple_digest="tuple-next",
        ),
    )

    _status, payload = _get(f"{base}/api/comments/feat_001")
    row = next(row for row in payload["comments"] if row["id"] == created["comment_id"])
    assert row["freshness"] == "outdated"
    assert row["outdated_reason"] == "review_tuple_mismatch"


def test_stale_semantic_thread_lifecycle_survives_restart(
    war_room_server, monkeypatch
) -> None:
    base, root, server = war_room_server
    original = _review_payload("feat_001")
    anchor = build_semantic_thread_anchor(
        original, kind="relationship", target_key="relationship.calls",
        source_side="proposed",
    ).to_dict()
    _status, created = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "body": "keep blocking", "blocking": True,
         "semantic_anchor": anchor},
    )

    drifted_side = replace(original.views[0].proposed, revision="c" * 40)
    drifted = replace(
        original,
        repositories=({"side": "proposed", "repository_key": "architecture-docs", "revision": "c" * 40},),
        views=(replace(original.views[0], proposed=drifted_side),),
    )
    monkeypatch.setattr(
        "cascade.war_room.architecture_routes.resolve_review_context",
        lambda _root, _work_id: drifted,
    )
    server.shutdown()
    server.server_close()
    port = _free_port()
    restarted = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=restarted.serve_forever, daemon=True)
    thread.start()
    restarted_base = f"http://127.0.0.1:{port}"
    try:
        _status, payload = _get(f"{restarted_base}/api/comments/feat_001")
        root_row = next(row for row in payload["comments"] if row["id"] == created["comment_id"])
        assert root_row["freshness"] == "outdated"
        assert root_row["outdated_reason"] == "revision_mismatch"
        assert root_row["blocking"] is True
        assert root_row["semantic_anchor"]["original_diff_link"] == "/diff/model-a..model-b"

        assert _post(
            f"{restarted_base}/api/comment",
            {"doc_id": "feat_001", "parent": created["comment_id"], "body": "still relevant"},
        )[0] == HTTPStatus.ACCEPTED
        assert _post(
            f"{restarted_base}/api/comment/resolve",
            {"doc_id": "feat_001", "comment_id": created["comment_id"]},
        )[0] == HTTPStatus.ACCEPTED
        assert _post(
            f"{restarted_base}/api/comment/reopen",
            {"doc_id": "feat_001", "comment_id": created["comment_id"]},
        )[0] == HTTPStatus.ACCEPTED
        _status, reopened = _get(f"{restarted_base}/api/comments/feat_001")
        reopened_root = next(row for row in reopened["comments"] if row["id"] == created["comment_id"])
        assert reopened_root["state"] == "open"
        assert reopened_root["freshness"] == "outdated"
        assert reopened_root["blocking"] is True
    finally:
        restarted.shutdown()
        restarted.server_close()
        thread.join(timeout=5)


def test_reply_inherits_parent_section_and_anchor(war_room_server) -> None:
    base, _root, _server = war_room_server
    status, root_body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "section": "Scope",
            "anchor": "quoted snippet",
            "body": "root thread",
            "line_start": 1,
            "line_end": 3,
            "doc_sha": "ignored-on-reply",
            "blocks": ["task_001"],
        },
    )
    assert status == HTTPStatus.ACCEPTED
    root_id = root_body["comment_id"]

    status, reply_body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "parent": root_id,
            "body": "human reply",
            "section": "ignored",
            "anchor": "ignored",
            "blocking": True,
            "line_start": 9,
            "line_end": 10,
            "doc_sha": "ignored",
            "blocks": ["task_999"],
        },
    )
    assert status == HTTPStatus.ACCEPTED
    reply_id = reply_body["comment_id"]

    _status, payload = _get(f"{base}/api/comments/feat_001")
    reply = next(c for c in payload["comments"] if c["id"] == reply_id)
    assert reply["section"] == "scope"
    assert reply["anchor"] == "quoted snippet"
    assert reply["parent"] == root_id
    assert reply["line_start"] is None
    assert reply["line_end"] is None
    assert reply["doc_sha"] is None
    assert reply["blocks"] == []


def test_reply_missing_parent_returns_404(war_room_server) -> None:
    base, _root, _server = war_room_server
    code, err = _post_expect_error(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "parent": "cmt_999", "body": "orphan reply"},
    )
    assert code == HTTPStatus.NOT_FOUND
    assert "error" in err


def test_root_empty_section_returns_400(war_room_server) -> None:
    base, _root, _server = war_room_server
    code, err = _post_expect_error(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "section": "   ", "body": "note"},
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "error" in err


def _review_payload(work_id: str) -> C4ReviewPayload:
    proposed = C4ReviewSide(
        "architecture-docs", "b" * 40, "artifacts/proposed.svg",
        (
            C4ReviewTarget("element", "element.system"),
            C4ReviewTarget("relationship", "relationship.calls"),
        ),
    )
    return C4ReviewPayload(
        state="ready", owner_work_id=work_id, authorized_owner="feature_architect",
        review_unit_id="architecture-review-exact", reviewed_tuple_digest="tuple-exact",
        repositories=({"side": "proposed", "repository_key": "architecture-docs", "revision": "b" * 40},),
        views=(C4ReviewView("context", "systemContextViews", "added", None, proposed),),
        changed_views=(("context", "systemContextViews"),), legend=(), summary="changed",
        requirements=("REQ-7",), decisions=(),
        diffs={"source": "/diff/model-a..model-b", "plan": "/diff/plan-a..plan-b", "model": {"identities": []}},
        provenance={"plan": {
            "repository_key": "plans",
            "revision": "p" * 40,
            "path": "docs/feature.md",
        }},
    )


def test_root_invalid_line_range_returns_400(war_room_server) -> None:
    base, _root, _server = war_room_server
    code, err = _post_expect_error(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "section": "Scope",
            "body": "note",
            "line_start": 5,
            "line_end": 3,
        },
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "error" in err


def test_comment_post_appends_graph_queue_events(war_room_server) -> None:
    base, root, _server = war_room_server
    status, root_body = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "section": "Scope", "body": "root"},
    )
    assert status == HTTPStatus.ACCEPTED
    root_id = root_body["comment_id"]

    status, _reply_body = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "parent": root_id, "body": "reply"},
    )
    assert status == HTTPStatus.ACCEPTED

    events, _ = read_events("feat_001", 0, root=root)
    types = [event.type for event in events]
    assert "CommentPosted" in types
    assert "CommentReplied" in types
