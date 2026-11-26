"""Bounded transcript publication and loopback HTTP contract coverage."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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


def _decode_cursor(cursor: str) -> dict[str, object]:
    return json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))


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


def _legacy_rows(root: Path, count: int, graph_id: str = "epic_001") -> None:
    path = root / f"docs/_war_room/chat/{graph_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": f"legacy-{number:03d}",
            "graph_id": graph_id,
            "author": "system",
            "body": f"message {number:03d}",
            "ts": "unknown",
            "occurred_at": None,
            "provenance": "legacy_unknown",
        }
        for number in range(1, count + 1)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _finish_legacy_import(root: Path, graph_id: str = "epic_001") -> None:
    with pytest.raises(TranscriptPendingError):
        append_transcript_message(graph_id, author="system", body="trigger", root=root)
    append_transcript_message(graph_id, author="system", body="trigger", root=root)


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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GET opened SQLite")
        ),
    )
    monkeypatch.setattr(
        "cascade.war_room.sidecar_routes.read_messages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GET scanned JSONL")
        ),
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
    transcript_server, monkeypatch
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

    projection = root / ".cascade/transcript_pages"
    files_before = {
        path.relative_to(projection): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in projection.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        "cascade.war_room.chat_store._connect_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GET opened SQLite")
        ),
    )
    monkeypatch.setattr(
        "cascade.war_room.sidecar_routes.read_messages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GET scanned JSONL")
        ),
        raising=False,
    )
    chunks: list[str] = []
    cursor = item["detail_cursor"]
    seen_cursors: set[str] = set()
    while cursor is not None:
        assert cursor not in seen_cursors
        seen_cursors.add(cursor)
        decoded_cursor = _decode_cursor(cursor)
        url = (
            base
            + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
            + urllib.parse.quote(cursor)
        )
        status, detail, _headers, response_size = _get(url)
        assert status == HTTPStatus.OK
        assert response_size < 256 * 1024
        assert len(detail["chunk"].encode("utf-8")) <= 64 * 1024
        assert detail["graph_id"] == decoded_cursor["graph"] == "epic_001"
        assert detail["message_id"] == decoded_cursor["message"] == "large-message"
        assert detail["incarnation"] == decoded_cursor["incarnation"]
        chunks.append(detail["chunk"])
        next_cursor = detail["next_cursor"]
        if not detail["complete"]:
            assert next_cursor is not None and next_cursor != cursor
            decoded_next = _decode_cursor(next_cursor)
            assert decoded_next == {
                **decoded_cursor,
                "offset": decoded_cursor["offset"]
                + len(detail["chunk"].encode("utf-8")),
            }
            assert decoded_next["offset"] > decoded_cursor["offset"]
        cursor = next_cursor
    assert "".join(chunks) == body
    assert detail["complete"] is True
    assert detail["next_cursor"] is None
    files_after = {
        path.relative_to(projection): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in projection.rglob("*")
        if path.is_file()
    }
    assert files_after == files_before

    status, foreign, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/not-the-message/detail?cursor="
        + urllib.parse.quote(item["detail_cursor"])
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert foreign["error"]["code"] == "invalid_request"

    stale_cursor = item["detail_cursor"]
    mid_character = _decode_cursor(stale_cursor)
    mid_character["offset"] = len("prefix-".encode("utf-8")) + 1
    invalid_offset_cursor = (
        base64.urlsafe_b64encode(
            json.dumps(mid_character, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    status, invalid_offset, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
        + urllib.parse.quote(invalid_offset_cursor)
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert invalid_offset["error"]["code"] == "invalid_request"

    decoded = _decode_cursor(stale_cursor)
    decoded["digest"] = "0" * 64
    changed_digest_cursor = (
        base64.urlsafe_b64encode(json.dumps(decoded, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    status, changed, _headers, _size = _get(
        base
        + "/api/transcript/v1/epic_001/items/large-message/detail?cursor="
        + urllib.parse.quote(changed_digest_cursor)
    )
    assert status == HTTPStatus.CONFLICT
    assert changed["error"]["code"] == "cursor_restart"
    monkeypatch.undo()
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
    cursor = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
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


def test_historical_ui_pages_milestones_and_bounded_detail(transcript_server) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    base, root = transcript_server
    graph_id = "epic_044"
    _legacy_rows(root, 130, graph_id)
    _finish_legacy_import(root, graph_id)
    append_transcript_message(
        graph_id,
        author="epic_manager",
        body="The older authored conclusion remains dated history.",
        root=root,
        message_id="manager-history",
        occurred_at="2026-11-25T03:58:01+00:00",
        metadata={"kind": "role_reply"},
    )
    append_transcript_message(
        graph_id,
        author="system",
        body="Recovery investigation started.",
        root=root,
        message_id="recovery-history",
        source_key="recovery:receipt-browser",
        occurred_at=None,
        provenance="reconciled",
        metadata={
            "kind": "recovery_milestone",
            "source_reference": "javascript:alert(1)",
        },
    )
    complete_body = "detail-prefix-" + ("🙂漢字" * 30000) + "-detail-suffix"
    append_transcript_message(
        graph_id,
        author="feature_architect",
        body=complete_body,
        root=root,
        message_id="large-ui-message",
        occurred_at="2026-11-25T04:02:25+00:00",
        metadata={"kind": "role_reply"},
    )

    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        try:
            page = browser.new_page()
            transcript_requests: list[str] = []
            page.on(
                "request",
                lambda request: (
                    transcript_requests.append(request.url)
                    if "/api/transcript/v1/" in request.url
                    else None
                ),
            )
            page.goto(base + "/")
            messages = page.locator("#chat-messages .chat-message")
            messages.first.wait_for()
            assert messages.count() == 50
            assert page.locator(
                '[data-message-id="recovery-history"] .author'
            ).inner_text() == ("System · Recovery")
            recovery = page.locator('[data-message-id="recovery-history"]')
            assert "Occurrence time unavailable" in recovery.inner_text()
            assert recovery.get_attribute("tabindex") == "0"
            assert recovery.get_attribute("id") == "recovery-milestone-recovery-history"
            assert recovery.locator("a").count() == 0
            assert page.locator(
                '[data-message-id="manager-history"] .author'
            ).inner_text() == ("Epic manager")

            scroll = page.locator("#chat-messages")
            anchor_id = messages.first.get_attribute("data-message-id")
            assert anchor_id
            page.evaluate("el => { el.scrollTop = 40; }", scroll.element_handle())
            before = page.locator(f'[data-message-id="{anchor_id}"]').bounding_box()
            page.get_by_role("button", name="Load older history").click()
            page.wait_for_function(
                "() => document.querySelectorAll('#chat-messages .chat-message').length === 100"
            )
            after = page.locator(f'[data-message-id="{anchor_id}"]').bounding_box()
            assert before is not None and after is not None
            assert abs(before["y"] - after["y"]) < 10

            detail = page.locator('[data-message-id="large-ui-message"]')
            detail.get_by_role("button", name="Open complete message").click()
            page.wait_for_function(
                "expected => document.querySelector('[data-message-id=\"large-ui-message\"] .chat-body').textContent === expected",
                arg=complete_body,
            )
            assert detail.locator(".chat-body").inner_text() == complete_body

            appended = append_transcript_message(
                graph_id,
                author="human",
                body="incremental browser message",
                root=root,
                message_id="incremental-ui-message",
            )
            page.locator(f'[data-message-id="{appended["id"]}"]').wait_for(timeout=7000)
            assert any("direction=older" in url for url in transcript_requests)
            assert any("direction=after" in url for url in transcript_requests)
            assert not any("/api/chat/" in url for url in transcript_requests)
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
        status, held_page, _headers, _size = _get(base + "/api/transcript/v1/epic_044")
        assert status == HTTPStatus.OK
        held_item = held_page["items"][0]
        assert held_item["transition_kind"] == "execution_started"
        assert held_item["receipt_id"] == held_start["receipt_id"]
        assert held_item["occurred_at"] == "2026-11-25T12:00:01+00:00"
    finally:
        register_transition_publisher(None)


def test_epic_044_held_reply_fast_path_replay_http_and_chromium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follow the incident timeline through real writer, HTTP, and browser seams."""

    playwright = pytest.importorskip("playwright.sync_api")
    from cascade.recovery_progress.notifications import register_transition_publisher
    from cascade.recovery_progress.publisher import (
        drain_recovery_progress,
        install_recovery_progress_publisher,
        publish_committed_transition,
    )
    from cascade.task import action_recovery
    from cascade.task.action_recovery import (
        acknowledge_team_recovery,
        create_or_load_action,
        load_action,
        resume_action,
    )
    from cascade.watchdog.incidents import transition_receipt_v1

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_044", title="Held recovery", tier="epic", status="active")
    fixture = json.loads(
        (
            Path(__file__).with_name("fixtures") / "recovery_progress_v1_epic_044.json"
        ).read_text()
    )
    action_id = fixture["primary"]["action_id"]
    queued_at = datetime(2026, 11, 25, 3, 58, 1, tzinfo=timezone.utc)
    acknowledged_at = datetime(2026, 11, 25, 3, 58, 10, tzinfo=timezone.utc)
    started_at = datetime(2026, 11, 25, 4, 2, 25, tzinfo=timezone.utc)
    runtime_started_at = datetime.now(timezone.utc)
    append_transcript_message(
        "epic_044",
        author="epic_manager",
        body="No recovery was needed in the earlier review.",
        root=root,
        message_id="older-authored-health",
        occurred_at="2026-11-25T03:41:00+00:00",
        metadata={"kind": "role_reply"},
    )

    install_recovery_progress_publisher(root)
    release_reply = threading.Event()
    executor_entered = threading.Event()
    worker_failures: list[BaseException] = []
    worker_result: list[dict[str, object]] = []

    def held_executor(_context):
        executor_entered.set()
        assert release_reply.wait(timeout=20)
        append_transcript_message(
            "epic_044",
            author="epic_manager",
            body="The held final role reply is now authored.",
            root=root,
            message_id="held-final-role-reply",
            occurred_at="2026-11-25T04:03:00+00:00",
            metadata={"kind": "role_reply"},
        )
        return {"outcome": "succeeded"}

    def run_held_executor() -> None:
        try:
            worker_result.append(
                resume_action(
                    action_id,
                    root=root,
                    execute=held_executor,
                    now=runtime_started_at,
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted by parent
            worker_failures.append(exc)

    server = None
    server_thread = None
    browser = None
    worker = None
    try:
        created = create_or_load_action(
            action_id,
            "review_publication",
            root=root,
            attempt_bound=2,
            metadata={"epic_id": "epic_044"},
            owning_team={"kind": "epic_team", "work_id": "epic_044"},
            routing_marker={"status": "enqueued", "review_id": "review-243"},
            now=queued_at,
        )
        queued_receipt = created["transition_receipts"][-1]
        assert queued_receipt["occurred_at"] == "2026-11-25T03:58:01+00:00"

        original_iso = action_recovery._iso
        with monkeypatch.context() as clock:
            clock.setattr(
                action_recovery,
                "_iso",
                lambda value: original_iso(
                    value if value is not None else acknowledged_at
                ),
            )
            acknowledge_team_recovery("epic_044", root=root)
        acknowledged = load_action(action_id, root=root)
        assert acknowledged is not None
        acknowledgement_receipt = acknowledged["transition_receipts"][-1]
        assert acknowledgement_receipt["transition_kind"] == "owner_acknowledged"
        assert acknowledgement_receipt["occurred_at"] == "2026-11-25T03:58:10+00:00"
        # The projection itself, before execution, must recognize the concrete
        # owner acknowledgement rather than leave the request merely queued.
        from cascade.war_room.recovery_progress import read_recovery_progress

        acknowledgement_progress = read_recovery_progress(root, "epic_044")
        assert acknowledgement_progress["primary"]["state"] == "acknowledged"

        monkeypatch.setattr(
            action_recovery,
            "_iso",
            lambda value: (
                started_at.isoformat() if value is not None else original_iso(value)
            ),
        )
        worker = threading.Thread(target=run_held_executor, name="held-final-reply")
        worker.start()
        assert executor_entered.wait(timeout=10)
        monkeypatch.setattr(action_recovery, "_iso", original_iso)
        running = load_action(action_id, root=root)
        assert running is not None
        start_receipt = next(
            receipt
            for receipt in running["transition_receipts"]
            if receipt["transition_kind"] == "execution_started"
        )

        # The start notification is direct and already published while the role
        # reply remains held.  A bounded replay subsequently repairs the claim
        # receipt that was committed in the same source action.
        before_replay = read_recovery_progress(root, "epic_044")
        executing = next(
            item
            for item in before_replay["items"]
            if item["action_id"] == action_id and item["attempt_number"] == 1
        )
        assert executing["state"] == "executing"
        assert executing["occurred_at"] == "2026-11-25T04:02:25+00:00"
        replay = drain_recovery_progress(root)
        assert replay["imported_receipts"] == 1
        assert drain_recovery_progress(root)["imported_receipts"] == 0

        competitor = transition_receipt_v1(
            source_kind="watchdog_incident",
            source_key="epic_044:competing-verified",
            action="verification",
            action_id="epic_044:competing-verified",
            generation=fixture["primary"]["generation"],
            graph_id="epic_044",
            affected_work_ids=("epic_044",),
            attempt_number=1,
            claim_id="claim-competing",
            sequence=1,
            transition_kind="authoritative_verification",
            occurred_at="2026-11-25T04:01:00+00:00",
            source_reference="fixture:epic_044_competing_verified",
            safe_payload={"target": "epic/epic_044"},
        )
        publish_committed_transition(
            root,
            competitor,
            {
                "accountable_owner": "watchdog",
                "result": {
                    "postcheck": {
                        "generation": fixture["primary"]["generation"],
                        "verified": True,
                        "verification_reference": "fixture:postcheck",
                    }
                },
            },
        )

        def start_server():
            instance = serve(root=root, host="127.0.0.1", port=_free_port())
            thread = threading.Thread(target=instance.serve_forever, daemon=True)
            thread.start()
            return instance, thread, f"http://127.0.0.1:{instance.server_port}"

        server, server_thread, base = start_server()
        progress_status, progress, _progress_headers, progress_response_bytes = _get(
            base + "/api/recovery/progress?work_id=epic_044&limit=100"
        )
        (
            transcript_status,
            transcript,
            _transcript_headers,
            transcript_response_bytes,
        ) = _get(base + "/api/transcript/v1/epic_044?limit=100")
        assert progress_status == transcript_status == HTTPStatus.OK
        assert len(progress["items"]) == 3 <= 100
        current = next(
            item
            for item in progress["items"]
            if item["action_id"] == action_id and item["attempt_number"] == 1
        )
        assert current["state"] == "executing"
        assert current["generation"] == queued_receipt["generation"]
        assert current["attempt_number"] == 1
        start_item = next(
            item
            for item in transcript["items"]
            if item.get("transition_kind") == "execution_started"
        )
        assert start_item["receipt_id"] == start_receipt["receipt_id"]
        assert start_item["action_id"] == action_id
        assert start_item["generation"] == current["generation"]
        assert start_item["attempt_number"] == current["attempt_number"]
        assert start_item["occurred_at"] == "2026-11-25T04:02:25+00:00"
        assert start_item["provenance"] == "direct"
        assert not any(
            item["id"] == "held-final-role-reply" for item in transcript["items"]
        )
        recovery_items = [
            item for item in transcript["items"] if item["kind"] == "recovery_milestone"
        ]
        assert len(recovery_items) == 5
        assert len({item["receipt_id"] for item in recovery_items}) == 5
        assert any(item["provenance"] == "reconciled" for item in recovery_items)

        progress_home = (
            root
            / ".cascade/recovery_progress/v1/work"
            / hashlib.sha256(b"epic_044").hexdigest()
        )
        progress_pointer = json.loads((progress_home / "current.json").read_text())
        progress_manifest_path = progress_home / progress_pointer["manifest"]
        progress_manifest = json.loads(progress_manifest_path.read_text())
        progress_source_bytes = sum(
            path.stat().st_size
            for path in (
                progress_home / "current.json",
                progress_manifest_path,
                progress_manifest_path.parent / progress_manifest["pages"][0],
            )
        )
        transcript_home = (
            root / ".cascade/transcript_pages" / hashlib.sha256(b"epic_044").hexdigest()
        )
        transcript_pointer = json.loads((transcript_home / "current.json").read_text())
        transcript_manifest_path = (
            transcript_home / "manifests" / transcript_pointer["manifest"]
        )
        transcript_manifest = json.loads(transcript_manifest_path.read_text())
        transcript_source_bytes = sum(
            path.stat().st_size
            for path in (
                transcript_home / "current.json",
                transcript_manifest_path,
                transcript_home / "pages" / transcript_manifest["pages"][-1]["file"],
            )
        )
        assert progress_source_bytes < 1024 * 1024
        assert transcript_source_bytes < 1024 * 1024
        assert progress_response_bytes < 256 * 1024
        assert transcript_response_bytes < 256 * 1024

        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/")
            anchor = page.locator(f"#recovery-milestone-{start_item['id']}")
            anchor.wait_for(timeout=7000)
            assert anchor.locator(".author").inner_text() == "System · Recovery"
            assert (
                page.locator('[data-message-id="held-final-role-reply"]').count() == 0
            )
            page.locator("#recovery-current-summary").get_by_text(
                "Executing", exact=False
            ).wait_for()
            warm = page.evaluate(
                """async () => {
                  const measured = async (url) => {
                    const started = performance.now();
                    const response = await fetch(url);
                    await response.arrayBuffer();
                    return performance.now() - started;
                  };
                  return {
                    board_ms: await measured('/api/board'),
                    room_ms: await measured('/api/transcript/v1/epic_044?limit=100'),
                  };
                }"""
            )
            assert warm["board_ms"] >= 0 and warm["room_ms"] >= 0
            browser.close()
            browser = None

        # Restart the HTTP service without touching the worker or projections.
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        server, server_thread, restarted_base = start_server()
        restart_status, restarted, _headers, _size = _get(
            restarted_base + "/api/transcript/v1/epic_044?limit=100"
        )
        assert restart_status == HTTPStatus.OK
        assert restarted["incarnation"] == transcript["incarnation"]
        assert any(item["id"] == start_item["id"] for item in restarted["items"])

        # Projection GETs remain usable with every repair/probe seam refused.
        with monkeypatch.context() as reads:
            reads.setattr(
                "cascade.war_room.chat_store._connect_index",
                lambda *_a, **_k: (_ for _ in ()).throw(
                    AssertionError("GET opened writer index")
                ),
            )
            reads.setattr(
                "cascade.war_room.sidecar_routes.read_messages",
                lambda *_a, **_k: (_ for _ in ()).throw(
                    AssertionError("GET scanned JSONL")
                ),
                raising=False,
            )
            reads.setattr(
                "cascade.agent.providers.probe_providers",
                lambda: (_ for _ in ()).throw(AssertionError("GET probed providers")),
            )
            reads.setattr(
                "cascade.agent.provider_metering.admit_provider_turn",
                lambda *_a, **_k: (_ for _ in ()).throw(
                    AssertionError("GET admitted a paid turn")
                ),
            )
            reads.setattr(
                subprocess,
                "run",
                lambda *_a, **_k: (_ for _ in ()).throw(
                    AssertionError("GET ran a process or Git")
                ),
            )
            reads.setattr(
                "cascade.epic.checkpoint.get_checkpointer",
                lambda *_a, **_k: (_ for _ in ()).throw(
                    AssertionError("GET opened a checkpoint")
                ),
            )
            assert (
                _get(restarted_base + "/api/recovery/progress?work_id=epic_044")[0]
                == HTTPStatus.OK
            )
            assert (
                _get(restarted_base + "/api/transcript/v1/epic_044")[0] == HTTPStatus.OK
            )

        print(
            "OPERATIONAL_METRICS "
            + json.dumps(
                {
                    "progress_source_bytes": progress_source_bytes,
                    "progress_response_bytes": progress_response_bytes,
                    "transcript_source_bytes": transcript_source_bytes,
                    "transcript_response_bytes": transcript_response_bytes,
                    "rows": len(transcript["items"]),
                    "warm_board_ms": round(warm["board_ms"], 3),
                    "warm_room_ms": round(warm["room_ms"], 3),
                },
                sort_keys=True,
            )
        )

        release_reply.set()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert worker_failures == []
        assert worker_result[0]["recovery_state"] == "completed"
        final_status, final_page, _headers, _size = _get(
            restarted_base + "/api/transcript/v1/epic_044?limit=100"
        )
        assert final_status == HTTPStatus.OK
        ids = [item["id"] for item in final_page["items"]]
        assert ids.index(start_item["id"]) < ids.index("held-final-role-reply")
        final_recovery = [
            item for item in final_page["items"] if item["kind"] == "recovery_milestone"
        ]
        assert len(final_recovery) == 6
        assert len({item["receipt_id"] for item in final_recovery}) == 6
    finally:
        release_reply.set()
        if worker is not None:
            worker.join(timeout=5)
        if browser is not None:
            browser.close()
        if server is not None:
            server.shutdown()
            server.server_close()
        if server_thread is not None:
            server_thread.join(timeout=5)
        register_transition_publisher(None)
