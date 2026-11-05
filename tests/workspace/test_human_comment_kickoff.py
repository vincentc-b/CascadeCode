"""Human comment kickoff via watchdog (feat_020 / task_088)."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cascade.agent.types import RoleResult
from cascade.comments import comment, reply_comment, resolve_comment
from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions
from cascade.watchdog import activate_epic, append_event, read_events
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory, watchdog_tick
from cascade.watchdog.types import Event
from cascade.war_room.server import serve
from cascade.workspace.kickoff import (
    deliver_queue_kickoffs,
    install_kickoff,
    wait_for_background_kickoffs,
)
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _isolate_graphs() -> None:
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()
    yield
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _commit_all(root: Path, message: str = "docs") -> None:
    _git(root, "add", "-A")
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "nothing to commit" not in (result.stdout + result.stderr):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            result.stdout,
            result.stderr,
        )


def _seed_active_epic(root: Path) -> None:
    from tests.support import add_doc

    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    # Keep this comment-delivery fixture genuinely in flight.  An epic with no
    # child features is immediately eligible for completion reconciliation when
    # the War Room starts, so it cannot receive a subsequent planning kickoff.
    add_doc(
        root,
        id="feat_001",
        title="Pending feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    _commit_all(root)


def _patch_run_role(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(
        return_value=RoleResult(text="model-output", status="finished"),
    )

    async def _wrapped(turn):  # type: ignore[no-untyped-def]
        return await mock(turn)

    # These delivery tests replace provider execution; no local authentication is needed.
    from cascade.agent.discovery.inventory import (
        InventoryFreshness, ProviderInventoryItem, ProviderInventoryResult,
    )
    from cascade.agent.discovery.types import DiscoveredModel

    inventory = ProviderInventoryResult(
        providers=(ProviderInventoryItem(
            provider_id="cursor", display_name="Test provider",
            models=tuple(DiscoveredModel(id=f"proj-{tier}", display_name=tier)
                         for tier in ("epic", "feature", "task")),
        ),),
        failures=(), freshness=InventoryFreshness(False, 0, 300, 300),
    )
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory)
    monkeypatch.setattr("cascade.agent.execution_preflight.refresh_provider_inventory", lambda: inventory)
    monkeypatch.setattr("cascade.agent.adapter.run_role", _wrapped)
    monkeypatch.setattr("cascade.agent.planning_turn.run_role", _wrapped)
    return mock


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_human_comment_watchdog_delivery_no_agent_or_resolve_kickoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_active_epic(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert wait_for_background_kickoffs(timeout=15)
    run_role_mock.reset_mock()

    root_id = comment(
        "epic_001",
        "scope",
        "please review",
        author="human",
        root=root,
        blocking=True,
    )
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    turns_after_human = run_role_mock.await_count
    assert turns_after_human >= 1

    reply_comment(
        "epic_001",
        root_id,
        "agent answer",
        author="epic_manager",
        root=root,
    )
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert run_role_mock.await_count == turns_after_human

    resolve_comment("epic_001", root_id, author="human", root=root)
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert run_role_mock.await_count == turns_after_human


def test_http_post_then_watchdog_tick_single_kickoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_active_epic(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert wait_for_background_kickoffs(timeout=15)
    run_role_mock.reset_mock()

    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        req = urllib.request.Request(
            f"{base}/api/comment",
            method="POST",
            data=json.dumps(
                {
                    "doc_id": "epic_001",
                    "section": "Intent",
                    "body": "war room note",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == HTTPStatus.ACCEPTED

        watchdog_tick(root)
        assert wait_for_background_kickoffs()
        turns_after_post = run_role_mock.await_count
        # One owning-team kickoff executes each of the two epic roles once.
        assert turns_after_post == 2
        assert sorted(call.args[0].role for call in run_role_mock.await_args_list) == [
            "epic_architect", "epic_manager",
        ]

        events, _ = read_events("epic_001", 0, root=root)
        assert sum(event.type == "CommentPosted" for event in events) == 1
        # Polling and reconnect reads use the same GET path and must be inert.
        for _ in range(5):
            with urllib.request.urlopen(f"{base}/api/comments/epic_001") as resp:
                assert resp.status == HTTPStatus.OK
                assert len(json.load(resp)["comments"]) == 1
        after_reads, _ = read_events("epic_001", 0, root=root)
        assert after_reads == events
        watchdog_tick(root)
        assert wait_for_background_kickoffs()
        assert run_role_mock.await_count == turns_after_post
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_non_comment_queue_event_still_kickoffs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_active_epic(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert wait_for_background_kickoffs(timeout=15)
    run_role_mock.reset_mock()

    append_event(
        "epic_001",
        Event(
            type="DecisionRecorded",
            ts=datetime.now(timezone.utc),
            payload={"section": "Decision log", "entry": "dec_001"},
            dest="epic_001",
        ),
        root=root,
    )
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert run_role_mock.await_count >= 1
