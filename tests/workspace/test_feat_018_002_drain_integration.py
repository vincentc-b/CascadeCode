"""Drain integration tests against a real ``cascade up`` subprocess (task_018_002_004)."""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.store import list_board, read_doc
from cascade.feature.checkpoint import thread_config
from cascade.feature.graph import ensure_feature_graph
from cascade.watchdog import append_event
from cascade.watchdog.types import Event
from tests.harness.cascade_up_subprocess import (
    get_supervisor_health,
    http_get,
    http_post_json,
    poll_until,
    poll_updating_post,
    prepare_drain_test_repo,
    start_cascade_up,
    start_cascade_up_on_root,
    touch_cascade_source,
    wait_for_worker_relaunch,
)
from tests.support import add_doc, commit_board


def _decision_count(epic_id: str, *, root: Path) -> int:
    body = read_doc(epic_id, root=root).body
    return len(re.findall(r"`dec_\d+`", body))


def _feature_children(epic_id: str, *, root: Path) -> list[str]:
    board = list_board(root=root)
    return [
        meta.id
        for meta in board.by_id.values()
        if meta.tier == "feature" and meta.parent == epic_id
    ]


def _feature_queue_marker_present(feature_id: str, marker: str, *, root: Path) -> bool:
    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    values = graph.get_state(config).values or {}
    for message in values.get("messages") or []:
        content = str(message.get("content") or "")
        if marker in content:
            return True
    return False


def _feature_graph_settled(feature_id: str, *, root: Path) -> bool:
    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    snapshot = graph.get_state(config)
    if snapshot.next:
        return False
    roles = {m.get("role") for m in (snapshot.values or {}).get("messages") or []}
    return "feature_architect" in roles


def test_in_flight_write_survives_drain_and_new_writes_get_503_updating(tmp_path: Path) -> None:
    slow_started = tmp_path / "slow_started"
    proc = start_cascade_up(
        tmp_path,
        enable_drain_routes=True,
        extra_env={
            "CASCADE_DRAIN_SLOW_STARTED": str(slow_started),
            "CASCADE_DRAIN_SLOW_SECONDS": "1.5",
        },
    )
    slow_done = proc.root / ".cascade" / "drain_slow_write.done"
    token = "in-flight-token"
    result: dict[str, object] = {}
    error: list[BaseException] = []

    def _slow_post() -> None:
        try:
            status, headers, body = http_post_json(
                f"{proc.base}/api/drain_test_slow_write",
                {"token": token},
            )
            result["status"] = status
            result["headers"] = headers
            result["body"] = body
        except BaseException as exc:  # pragma: no cover - surfaced in assertion
            error.append(exc)

    try:
        worker_before = proc.worker_pid
        assert worker_before is not None
        writer = threading.Thread(target=_slow_post, daemon=True)
        writer.start()
        poll_until(lambda: slow_started.is_file(), timeout=10.0)
        touch_cascade_source(proc.install_root)
        poll_updating_post(proc.base)
        health_status, health = get_supervisor_health(proc.base)
        assert health_status == 200
        assert health is not None
        assert health.get("state") in ("serving", "draining", "restarting")
        get_status, get_headers, _ = http_get(f"{proc.base}/api/health")
        assert get_status == 200
        assert get_headers.get("connection", "").lower() == "close"
        get_status, get_headers, _ = http_get(f"{proc.base}/api/board")
        assert get_status == 200
        assert get_headers.get("connection", "").lower() == "close"
        writer.join(timeout=20.0)
        assert not error, error[0]
        assert result.get("status") == 200
        assert slow_done.read_text(encoding="utf-8").strip() == token
        wait_for_worker_relaunch(proc, worker_before)
    finally:
        stderr = proc.stop()
        assert proc.launcher.returncode == 0, stderr


def test_replay_safe_tools_resume_once_after_drain_cancel(tmp_path: Path) -> None:
    block_file = tmp_path / "fake_block"
    block_file.write_text("block\n", encoding="utf-8")
    root = prepare_drain_test_repo(tmp_path)
    epic_id = "epic_018"
    add_doc(root, id=epic_id, title="Drain epic", tier="epic", status="ready_to_plan")
    commit_board(root, message="seed epic")
    proc = start_cascade_up_on_root(
        tmp_path,
        root,
        extra_env={"CASCADE_FAKE_BLOCK_FILE": str(block_file)},
    )
    try:
        worker_before = proc.worker_pid
        assert worker_before is not None
        status, _, body = http_post_json(
            f"{proc.base}/api/activate_epic",
            {"id": epic_id},
        )
        assert status == 200 and body.get("ok") is True

        def _tools_applied() -> bool:
            return _decision_count(epic_id, root=proc.root) == 1 and len(
                _feature_children(epic_id, root=proc.root)
            ) == 1

        poll_until(_tools_applied, timeout=30.0)
        touch_cascade_source(proc.install_root)
        wait_for_worker_relaunch(proc, worker_before)
        block_file.unlink(missing_ok=True)

        def _architect_finished() -> bool:
            doc = read_doc(epic_id, root=proc.root)
            return doc.meta.status != "failed" and _decision_count(epic_id, root=proc.root) == 1

        poll_until(_architect_finished, timeout=30.0)
        assert len(_feature_children(epic_id, root=proc.root)) == 1
        for feature_id in _feature_children(epic_id, root=proc.root):
            feature = read_doc(feature_id, root=proc.root)
            assert feature.meta.status != "failed"
    finally:
        stderr = proc.stop()
        assert proc.launcher.returncode == 0, stderr


def test_queue_event_during_drain_delivered_after_restart(tmp_path: Path) -> None:
    slow_started = tmp_path / "queue_probe_slow_started"
    root = prepare_drain_test_repo(tmp_path)
    epic_id = "epic_018"
    feature_id = "feat_018_002"
    marker = "drain_queue_marker_c"
    add_doc(root, id=epic_id, title="Queue epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id=feature_id,
        title="Queue feature",
        tier="feature",
        status="ready_to_plan",
        parent=epic_id,
    )
    commit_board(root, message="seed queue board")
    proc = start_cascade_up_on_root(
        tmp_path,
        root,
        enable_drain_routes=True,
        extra_env={
            "CASCADE_DRAIN_SLOW_STARTED": str(slow_started),
            "CASCADE_DRAIN_SLOW_SECONDS": "1.5",
        },
    )
    slow_errors: list[BaseException] = []

    def _hold_drain_open() -> None:
        try:
            http_post_json(
                f"{proc.base}/api/drain_test_slow_write",
                {"token": "queue-probe"},
            )
        except BaseException as exc:  # pragma: no cover - surfaced in assertion
            slow_errors.append(exc)

    try:
        worker_before = proc.worker_pid
        assert worker_before is not None
        assert http_post_json(
            f"{proc.base}/api/activate_epic",
            {"id": epic_id},
        )[0] == 200
        assert http_post_json(
            f"{proc.base}/api/approve_feature",
            {"id": feature_id},
        )[0] == 200
        assert http_post_json(
            f"{proc.base}/api/dispatch_feature",
            {"id": feature_id},
        )[0] == 200
        poll_until(lambda: _feature_graph_settled(feature_id, root=proc.root), timeout=30.0)
        slow_writer = threading.Thread(target=_hold_drain_open, daemon=True)
        slow_writer.start()
        poll_until(lambda: slow_started.is_file(), timeout=10.0)
        touch_cascade_source(proc.install_root)
        poll_updating_post(proc.base)
        append_event(
            feature_id,
            Event(
                type="DrainQueueProbe",
                ts=datetime.now(timezone.utc),
                payload={"marker": marker},
                dest=feature_id,
            ),
            root=proc.root,
        )
        wait_for_worker_relaunch(proc, worker_before)
        slow_writer.join(timeout=20.0)
        assert not slow_errors, slow_errors[0]
        poll_until(
            lambda: _feature_queue_marker_present(feature_id, marker, root=proc.root),
            timeout=30.0,
        )
    finally:
        stderr = proc.stop()
        assert proc.launcher.returncode == 0, stderr
