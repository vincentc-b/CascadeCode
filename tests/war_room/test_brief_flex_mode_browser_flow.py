"""Focused UI/system coverage for capability-gated brief flex mode."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cascade.agent.discovery.inventory import clear_provider_inventory_cache, get_provider_inventory
from cascade.agent.discovery.types import DiscoveredModel, ProviderDiscoverySnapshot
from cascade.board.store import read_doc, reset_id_reservations
from cascade.watchdog.model_resolve import resolve_backend
from cascade.war_room.server import serve
from tests.agent.test_provider_inventory import _fake_discover, _unavailable
from tests.support import add_doc, make_repo
from tests.war_room.test_brief_full_stack_defaults_e2e import _create_brief_on_board
from tests.war_room.test_http_read import _free_port

_FLOW = Path(__file__).with_name("brief_flex_mode_browser_flow.mjs")


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    clear_provider_inventory_cache()
    reset_id_reservations()
    yield
    clear_provider_inventory_cache()
    reset_id_reservations()


def _patch_capability_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    models = tuple(
        DiscoveredModel(id=model_id, display_name=model_id)
        for model_id in (
            "gpt-manager",
            "gpt-architect",
            "gpt-feature-lead",
            "gpt-feature-architect",
            "gpt-swe",
        )
    )
    mapping = {
        "codex": ProviderDiscoverySnapshot(
            provider_id="codex",
            available=True,
            models=models,
            supports_flex_mode=True,
        ),
        "cursor": ProviderDiscoverySnapshot(
            provider_id="cursor",
            available=True,
            models=models,
            supports_flex_mode=False,
        ),
        "claude": _unavailable("claude", failure="not_authenticated"),
    }

    def inventory(**kwargs: object) -> object:
        return get_provider_inventory(
            discover=_fake_discover(mapping),
            ttl_seconds=60.0,
            now=10.0,
            force_refresh=bool(kwargs.get("force_refresh")),
        )

    monkeypatch.setattr("cascade.briefs.get_provider_inventory", inventory)


def test_flex_mode_editor_capability_persistence_and_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH")

    root = make_repo(tmp_path, git=True)
    add_doc(root, id="epic_001", title="Existing", tier="epic")
    _patch_capability_inventory(monkeypatch)
    monkeypatch.setattr("cascade.briefs.create_brief", _create_brief_on_board)

    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [node, str(_FLOW)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "WAR_ROOM_BASE": f"http://127.0.0.1:{port}"},
        )
        assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    saved_path = next(
        (root / "docs" / "epics" / "1_backlog").glob("*_flex_editor_system_test.md")
    )
    saved_id = saved_path.name.split("_flex_editor", 1)[0]
    saved = read_doc(saved_id, root=root)
    assert saved.meta.flex_mode is False
    assert resolve_backend("epic_manager", saved.meta, root=root).flex_mode is False
