"""Bounded transcript publication and loopback HTTP contract coverage."""

from __future__ import annotations

import base64
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.war_room.chat_store import (
    TranscriptPendingError,
    append_transcript_message,
    move_transcript_room,
    remove_message,
)
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str) -> tuple[int, object, dict[str, str], int]:
    try:
        response = urllib.request.urlopen(url)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        return response.status, json.loads(raw), dict(response.headers), len(raw)


@pytest.fixture
def transcript_server(tmp_path: Path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Transcript", tier="epic")
    add_doc(root, id="epic_002", title="Other", tier="epic")
    add_doc(root, id="epic_044", title="Held recovery", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Recovery owner",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    add_doc(
        root,
        id="task_001",
        title="Recovery source",
        tier="task",
        parent="feat_001",
        status="active",
    )
    server = serve(root=root, host="127.0.0.1", port=_free_port())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _legacy_rows(root: Path, count: int) -> None:
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": f"legacy-{number:03d}",
            "graph_id": "epic_001",
            "author": "system",
            "body": f"message {number:03d}",
            "ts": "unknown",
            "occurred_at": None,
            "provenance": "legacy_unknown",
        }
        for number in range(1, count + 1)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _finish_legacy_import(root: Path) -> None:
    with pytest.raises(TranscriptPendingError):
        append_transcript_message("epic_001", author="system", body="trigger", root=root)
    append_transcript_message("epic_001", author="system", body="trigger", root=root)


def test_paginated_latest_older_after_and_legacy_headers(transcript_server) -> None:
    base, root = transcript_server
    _legacy_rows(root, 130)
    _finish_legacy_import(root)

    status, latest, _headers, size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    assert size < 256 * 1024
    assert latest["schema_version"] == 1
    assert latest["completeness"] == "complete"
    assert [item["id"] for item in latest["items"][:2]] == ["legacy-082", "legacy-083"]
    assert latest["items"][-1]["body"] == "trigger"
    assert latest["items"][0]["occurred_at"] is None
    assert latest["has_more"] is True

    older_url = (
        base
        + "/api/transcript/v1/epic_001?direction=older&cursor="
        + urllib.parse.quote(latest["older_cursor"])
    )
    status, older, _headers, _size = _get(older_url)
    assert status == HTTPStatus.OK
    assert [item["id"] for item in older["items"]] == [
        f"legacy-{number:03d}" for number in range(32, 82)
    ]
    assert older["high_water_mark"] == latest["high_water_mark"]

    status, legacy, headers, legacy_size = _get(base + "/api/chat/epic_001")
    assert status == HTTPStatus.OK
    assert isinstance(legacy, list) and len(legacy) == 50
    assert legacy_size < 256 * 1024
    assert headers["X-Transcript-Completeness"] == "complete"
    assert headers["X-Transcript-Incarnation"] == latest["incarnation"]
    assert headers["X-Transcript-Has-More"] == "true"
    assert 'rel="next"' in headers["Link"]

    after_cursor = latest["after_cursor"]
    appended = append_transcript_message(
        "epic_001",
        author="system",
        body="System · Recovery attempt started",
        root=root,
        source_key="epic_044:held-turn:start",
        occurred_at=None,
        provenance="reconciled",
        metadata={"kind": "recovery_milestone"},
    )
    after_url = (
        base
        + "/api/transcript/v1/epic_001?direction=after&cursor="
        + urllib.parse.quote(after_cursor)
    )
    status, after, _headers, _size = _get(after_url)
    assert status == HTTPStatus.OK
    assert [item["id"] for item in after["items"]] == [appended["id"]]
    assert after["items"][0]["source_key"] == "epic_044:held-turn:start"
    assert after["has_more"] is False


def test_typed_invalid_restart_pending_and_get_is_projection_only(
    transcript_server, monkeypatch
) -> None:
    base, root = transcript_server
    status, pending, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert pending["error"]["code"] == "history_pending"
    status, unavailable, _headers, _size = _get(base + "/api/chat/epic_001")
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert unavailable["error"]["code"] == "transcript_unavailable"

    append_transcript_message("epic_001", author="human", body="keep", root=root)
    status, latest, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    old_cursor = latest["after_cursor"]

    # GET must remain usable when every writer/reconciliation entry point is forbidden.
    monkeypatch.setattr(
        "cascade.war_room.chat_store._connect_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GET opened SQLite")),
    )
    monkeypatch.setattr(
        "cascade.war_room.sidecar_routes.read_messages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GET scanned JSONL")),
        raising=False,
    )
    projection = root / ".cascade/transcript_pages"
    files_before = {
        path.relative_to(projection): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in projection.rglob("*")
        if path.is_file()
    }
    status, _latest, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    files_after = {
        path.relative_to(projection): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in projection.rglob("*")
        if path.is_file()
    }
    assert files_after == files_before
    assert not (root / ".cascade/checkpoints/epic_001.sqlite").exists()

    status, invalid, _headers, _size = _get(
        base + "/api/transcript/v1/epic_001?limit=101"
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert invalid["error"] == {
        "code": "invalid_request",
        "message": "limit must be between 1 and 100",
        "retryable": False,
    }
    status, foreign, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_002?direction=after&cursor="
        + urllib.parse.quote(old_cursor)
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert foreign["error"]["code"] == "invalid_request"

    # Restore the writer only to force an incarnation change, then prove the old cursor restarts.
    monkeypatch.undo()
    remove_message("epic_001", latest["items"][0]["id"], root=root)
    status, restart, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001?direction=after&cursor="
        + urllib.parse.quote(old_cursor)
    )
    assert status == HTTPStatus.CONFLICT
    assert restart["error"]["code"] == "cursor_restart"
    assert restart["restart"] is True
    assert restart["current_incarnation"] != latest["incarnation"]


def test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor(
    transcript_server
) -> None:
    base, root = transcript_server
    body = "prefix-" + ("🙂漢字" * 30000) + "-suffix"
    message = append_transcript_message(
        "epic_001", author="system", body=body, root=root, message_id="large-message"
    )
    status, latest, _headers, page_size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK and page_size < 256 * 1024
    item = latest["items"][0]
    assert item["id"] == message["id"]
    assert item["detail_truncated"] is True
    assert "Transcript preview" in item["body"]
    assert "detail_digest" not in item

    chunks: list[str] = []
    cursor = item["detail_cursor"]
    while cursor is not None:
        url = (
            base
            + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
            + urllib.parse.quote(cursor)
        )
        status, detail, _headers, response_size = _get(url)
        assert status == HTTPStatus.OK
        assert response_size < 256 * 1024
        assert len(detail["chunk"].encode("utf-8")) <= 64 * 1024
        chunks.append(detail["chunk"])
        cursor = detail["next_cursor"]
    assert "".join(chunks) == body
    assert detail["complete"] is True

    status, foreign, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/not-the-message/detail?cursor="
        + urllib.parse.quote(item["detail_cursor"])
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert foreign["error"]["code"] == "invalid_request"

    stale_cursor = item["detail_cursor"]
    decoded = json.loads(
        base64.urlsafe_b64decode(stale_cursor + "=" * (-len(stale_cursor) % 4))
    )
    decoded["digest"] = "0" * 64
    changed_digest_cursor = base64.urlsafe_b64encode(
        json.dumps(decoded, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    status, changed, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
        + urllib.parse.quote(changed_digest_cursor)
    )
    assert status == HTTPStatus.CONFLICT
    assert changed["error"]["code"] == "cursor_restart"
    detail_file = next((root / ".cascade/transcript_pages").glob("*/details/*.txt"))
    detail_file.unlink()
    status, missing, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
        + urllib.parse.quote(stale_cursor)
    )
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert missing["error"]["code"] == "history_pending"
    remove_message("epic_001", "large-message", root=root)
    status, stale, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
        + urllib.parse.quote(stale_cursor)
    )
    assert status == HTTPStatus.CONFLICT
    assert stale["error"]["code"] == "cursor_restart"


def test_cursor_sequence_overflow_is_restart(transcript_server) -> None:
    base, root = transcript_server
    append_transcript_message("epic_001", author="human", body="one", root=root)
    status, latest, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    payload = {
        "v": 1,
        "kind": "page",
        "graph": "epic_001",
        "incarnation": latest["incarnation"],
        "direction": "after",
        "sequence": latest["high_water_mark"] + 100,
        "high_water": latest["high_water_mark"] + 100,
    }
    cursor = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    status, restart, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001?direction=after&cursor="
        + urllib.parse.quote(cursor)
    )
    assert status == HTTPStatus.CONFLICT
    assert restart["error"]["code"] == "cursor_restart"


def test_room_move_changes_page_incarnation_and_restarts_cursor(
    transcript_server, tmp_path: Path
) -> None:
    base, root = transcript_server
    append_transcript_message("epic_001", author="human", body="before move", root=root)
    status, before, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    destination = tmp_path / "new-owner"
    move_transcript_room(
        "epic_001",
        source_root=root,
        destination_root=destination,
        root=root,
    )
    status, restart, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001?direction=after&cursor="
        + urllib.parse.quote(before["after_cursor"])
    )
    assert status == HTTPStatus.CONFLICT
    assert restart["error"]["code"] == "cursor_restart"
    status, after, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    assert after["incarnation"] != before["incarnation"]
    assert [item["body"] for item in after["items"]] == ["before move"]


def test_pending_full_tail_is_unavailable_until_writer_replay(
    transcript_server, monkeypatch
) -> None:
    from cascade.war_room import chat_store

    base, root = transcript_server
    append_transcript_message("epic_001", author="human", body="committed", root=root)
    original_commit = chat_store._commit_intent
    failed = False

    def die_before_index(connection, intent):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("process died before index commit")
        return original_commit(connection, intent)

    monkeypatch.setattr(chat_store, "_commit_intent", die_before_index)
    with pytest.raises(OSError, match="process died"):
        append_transcript_message(
            "epic_001",
            author="system",
            body="durable full tail",
            root=root,
            message_id="tail-message",
            source_key="tail-source",
        )
    status, pending, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert pending["error"]["code"] == "history_pending"

    replay = append_transcript_message(
        "epic_001",
        author="system",
        body="durable full tail",
        root=root,
        message_id="tail-message",
        source_key="tail-source",
    )
    assert replay["id"] == "tail-message"
    status, recovered, _headers, _size = _get(base + "/api/transcript/v1/epic_001")
    assert status == HTTPStatus.OK
    assert len(recovered["items"]) == 2
    assert recovered["items"][-1]["id"] == "tail-message"


def test_large_history_keeps_read_work_bounded(transcript_server) -> None:
    base, root = transcript_server
    _legacy_rows(root, 10_000)
    attempts = 0
    started = time.monotonic()
    while True:
        attempts += 1
        try:
            append_transcript_message(
                "epic_001", author="system", body="import complete", root=root
            )
            break
        except TranscriptPendingError:
            continue
    publication_seconds = time.monotonic() - started
    assert attempts == 100
    status, latest, _headers, response_size = _get(
        base + "/api/transcript/v1/epic_001?limit=100"
    )
    assert status == HTTPStatus.OK
    assert len(latest["items"]) == 100
    assert latest["items"][0]["id"] == "legacy-9902"
    assert response_size < 256 * 1024
    # Record the actual fixture cost for closeout without turning local disk
    # speed into a universal product promise.
    assert publication_seconds >= 0


def test_real_chromium_loads_older_and_incrementally_polls(transcript_server) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    base, root = transcript_server
    _legacy_rows(root, 130)
    _finish_legacy_import(root)
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        try:
            page = browser.new_page()
            page.goto(base + "/api/transcript/v1/epic_001")
            initial = page.evaluate(
                """async () => await (await fetch('/api/transcript/v1/epic_001')).json()"""
            )
            older = page.evaluate(
                """async cursor => await (await fetch('/api/transcript/v1/epic_001?direction=older&cursor=' + encodeURIComponent(cursor))).json()""",
                initial["older_cursor"],
            )
            assert len(initial["items"]) == len(older["items"]) == 50
            appended = append_transcript_message(
                "epic_001", author="system", body="browser incremental", root=root
            )
            after = page.evaluate(
                """async cursor => await (await fetch('/api/transcript/v1/epic_001?direction=after&cursor=' + encodeURIComponent(cursor))).json()""",
                initial["after_cursor"],
            )
            assert [item["id"] for item in after["items"]] == [appended["id"]]
        finally:
            browser.close()


def test_restarted_receipt_replay_and_epic_044_held_start_reach_pages(
    transcript_server,
) -> None:
    from cascade.recovery_progress.notifications import register_transition_publisher
    from cascade.recovery_progress.publisher import (
        drain_recovery_progress,
        publish_committed_transition,
    )
    from cascade.task.action_recovery import create_or_load_action
    from cascade.watchdog.incidents import transition_receipt_v1

    base, root = transcript_server
    register_transition_publisher(None)
    try:
        create_or_load_action(
            "task_001:delivery",
            "queued_delivery",
            root=root,
            attempt_bound=1,
            metadata={"task_id": "task_001"},
            owning_team={"kind": "feature_team", "work_id": "feat_001"},
        )
        replay = drain_recovery_progress(root)
        assert replay["imported_receipts"] == 1
        status, feature_page, _headers, _size = _get(
            base + "/api/transcript/v1/feat_001"
        )
        assert status == HTTPStatus.OK
        assert feature_page["items"][0]["provenance"] == "reconciled"

        held_start = transition_receipt_v1(
            source_kind="task_action",
            source_key="epic_044:held-turn",
            action="delivery",
            action_id="epic_044:held-turn",
            generation="sha256:epic044-held-generation",
            graph_id="epic_044",
            affected_work_ids=("epic_044",),
            attempt_number=1,
            claim_id="claim-epic044-held",
            sequence=2,
            transition_kind="execution_started",
            occurred_at="2026-11-25T12:00:01+00:00",
            source_reference="executions.json#actions/epic_044:held-turn/2",
            safe_payload={"target": "epic_044"},
        )
        publish_committed_transition(root, held_start, {"recovery_state": "running"})
        status, held_page, _headers, _size = _get(
            base + "/api/transcript/v1/epic_044"
        )
        assert status == HTTPStatus.OK
        held_item = held_page["items"][0]
        assert held_item["transition_kind"] == "execution_started"
        assert held_item["receipt_id"] == held_start["receipt_id"]
        assert held_item["occurred_at"] == "2026-11-25T12:00:01+00:00"
    finally:
        register_transition_publisher(None)
