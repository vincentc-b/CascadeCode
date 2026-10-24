"""Full-stack brief defaults: discovery, create, reload, downstream (task_006_002_004)."""

from __future__ import annotations

import subprocess
import threading
from http import HTTPStatus
from pathlib import Path

import pytest

import cascade.epic.mint  # noqa: F401
import cascade.feature.mint  # noqa: F401
from cascade.agent.discovery.inventory import clear_provider_inventory_cache
from cascade.board.store import read_doc, reset_id_reservations
from cascade.briefs import _next_epic_id, _slug, build_brief_doc, validate_brief
from cascade.epic.mint import mint_feature
from cascade.feature.mint import mint_task
from cascade.tracking import MergeRequest
from cascade.watchdog.model_resolve import resolve_backend
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo, write_default_models
from tests.war_room.test_brief_defaults_api import (
    _get,
    _patch_inventory,
    _post,
    _post_expect_error,
)
from tests.war_room.test_http_read import _free_port


@pytest.fixture(autouse=True)
def _clear_inventory_cache() -> None:
    clear_provider_inventory_cache()
    yield
    clear_provider_inventory_cache()


@pytest.fixture(autouse=True)
def _reset_ids() -> None:
    reset_id_reservations()
    yield
    reset_id_reservations()


@pytest.fixture
def brief_defaults_e2e_server(tmp_path: Path):
    root = make_repo(tmp_path, git=True)
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(root, id="feat_001", title="Beta", tier="feature", parent="epic_001", status="backlog")
    add_doc(root, id="task_001", title="Alpha", tier="task", parent="feat_001", status="active")
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


def _stack_models() -> dict[str, str]:
    return {
        "epic_manager": "gpt-manager",
        "epic_architect": "gpt-architect",
        "feature_lead": "gpt-feature-lead",
        "feature_architect": "gpt-feature-architect",
        "swe": "gpt-swe",
    }


def _brief_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Full stack defaults",
        "intent": "Prove inventory-backed brief defaults.",
        "success_criteria": "Selections persist and propagate to minted work.",
        "constraints": "",
        "provider": "codex",
        "models": _stack_models(),
    }
    payload.update(overrides)
    return payload


def _create_brief_on_board(root: Path, raw: dict[str, object]) -> tuple[str, MergeRequest]:
    from cascade.board.parse import render_doc

    request = validate_brief(raw, root=root)
    epic_id = _next_epic_id(root)
    path = root / "docs" / "epics" / "1_backlog" / f"{epic_id}_{_slug(request.title)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(build_brief_doc(request, epic_id, path)), encoding="utf-8")
    branch = f"cascade/brief/{epic_id}"
    return epic_id, MergeRequest(
        url=f"https://example.test/pull/{epic_id}",
        number="1",
        forge="github",
        source_branch=branch,
        target_branch="main",
        draft=True,
    )


def test_full_stack_brief_defaults_discovery_create_reload_and_downstream(
    brief_defaults_e2e_server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, root, _server = brief_defaults_e2e_server
    _patch_inventory(monkeypatch)
    write_default_models(root)
    monkeypatch.setattr("cascade.briefs.create_brief", _create_brief_on_board)

    status, inventory = _get(f"{base}/api/brief/inventory")
    assert status == HTTPStatus.OK
    assert inventory["loading"] is False
    assert {item["id"] for item in inventory["providers"]} == {"codex"}
    codex = inventory["providers"][0]
    swe_model = next(item for item in codex["models"] if item["id"] == "gpt-swe")
    assert swe_model["reasoning"]["override_levels"] == ["low", "high"]

    status, template = _get(f"{base}/api/brief/template")
    assert status == HTTPStatus.OK
    assert template["providers"] == ["codex"]
    assert template["provider"] == "codex"
    assert set(template["models"]) == set(_stack_models())

    stale = _brief_payload(models={**_stack_models(), "swe": "retired-model"})
    status, body = _post_expect_error(f"{base}/api/briefs", stale)
    assert status == HTTPStatus.BAD_REQUEST
    assert "not offered" in body["error"]

    valid = _brief_payload(reasoning={"swe": "high"})
    status, created = _post(f"{base}/api/briefs", valid)
    assert status == HTTPStatus.CREATED
    epic_id = created["epic_id"]

    status, reloaded = _get(f"{base}/api/brief/template?epic_id={epic_id}")
    assert status == HTTPStatus.OK
    saved = reloaded["saved"]
    assert saved["provider"] == "codex"
    assert saved["models"] == _stack_models()
    assert saved["reasoning"] == {"swe": "high"}

    epic = read_doc(epic_id, root=root)
    assert epic.meta.provider == "codex"
    assert epic.meta.models == _stack_models()
    assert epic.meta.reasoning == {"swe": "high"}

    feature_id = mint_feature("Downstream feature", epic_id=epic_id, root=root)
    feature = read_doc(feature_id, root=root)
    assert feature.meta.provider == "codex"
    assert feature.meta.models == {
        "feature_lead": "gpt-feature-lead",
        "feature_architect": "gpt-feature-architect",
    }

    task_id = mint_task("Downstream task", feature_id=feature_id, root=root)
    task = read_doc(task_id, root=root)
    assert task.meta.provider == "codex"
    assert task.meta.models == {"swe": "gpt-swe"}
    assert task.meta.reasoning == {"swe": "high"}

    backend = resolve_backend("swe", task.meta, root=root)
    assert backend.provider == "codex"
    assert backend.model.model_id == "gpt-swe"
    assert backend.model.source == "document-role"
    assert backend.reasoning == "high"
    assert backend.reasoning_source == "document-role"
