"""Focused API projection coverage for provider configuration readiness."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
    clear_provider_inventory_cache,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderCompatibilityEvidence,
    ProviderDiscoverySnapshot,
    ReasoningCapability,
)
from cascade.board.store import list_board, read_doc, write_doc
from cascade.briefs import fetch_brief_provider_inventory
from cascade.war_room.serialize import board_view_from_index
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _inventory_cache() -> None:
    clear_provider_inventory_cache()
    yield
    clear_provider_inventory_cache()


def _inventory(
    *, model: str | None, stale: bool = False, from_cache: bool = True
) -> ProviderInventoryResult:
    providers = (
        (
            ProviderInventoryItem(
                "codex",
                "Codex",
                (
                    DiscoveredModel(
                        model,
                        model,
                        reasoning=ReasoningCapability("medium", ("high",)),
                        supports_flex_mode=True,
                    ),
                ),
                supports_flex_mode=True,
            ),
        )
        if model is not None
        else ()
    )
    failures = (
        ()
        if model is not None
        else (ProviderInventoryFailure("codex", "not_authenticated"),)
    )
    return ProviderInventoryResult(
        providers=providers,
        failures=failures,
        freshness=InventoryFreshness(
            from_cache=from_cache,
            fetched_at=1.0 if not stale else None,
            expires_at=10_000_000_000.0 if not stale else None,
            ttl_seconds=300.0,
        ),
    )


def _configured_task(root, work_id: str, *, status: str = "backlog") -> None:
    board = list_board(root)
    if "epic_001" not in board.by_id:
        add_doc(root, id="epic_001", title="Epic", tier="epic", status=status)
        add_doc(
            root,
            id="feat_001",
            title="Feature",
            tier="feature",
            status=status,
            parent="epic_001",
        )
    add_doc(
        root,
        id=work_id,
        title=work_id,
        tier="task",
        status=status,
        parent="feat_001",
    )
    doc = read_doc(work_id, root=root)
    doc.meta = replace(
        doc.meta,
        provider="codex",
        models={"swe": "model-a"},
        reasoning={"swe": "high"},
        flex_mode=True,
    )
    write_doc(doc, root=root)


def _support_compatibility(monkeypatch) -> None:
    monkeypatch.setattr(
        "cascade.agent.selection_preflight.probe_provider_compatibility",
        lambda _provider: ProviderCompatibilityEvidence(True, True, True),
    )


def test_board_uses_one_inventory_snapshot_and_projects_complete_roles(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _configured_task(root, "task_001")
    _configured_task(root, "task_002")
    calls = []
    inventory = _inventory(model="model-a")
    monkeypatch.setattr(
        "cascade.war_room.serialize.get_provider_inventory",
        lambda: calls.append("inventory") or inventory,
    )
    _support_compatibility(monkeypatch)

    rows = board_view_from_index(list_board(root), root=root)["tasks"]["1_backlog"]

    assert calls == ["inventory"]
    assert {row["provider_readiness"]["outcome"] for row in rows} == {"supported"}
    for row in rows:
        readiness = row["provider_readiness"]
        assert readiness["action"] == "readiness"
        assert len(readiness["checks"]) == 1
        check = readiness["checks"][0]
        assert check["role"] == "swe"
        assert check["provider"] == "codex"
        assert check["model_id"] == "model-a"
        assert check["reasoning_level"] == "high"
        assert check["reasoning_effective"] == "high"
        assert check["reviewed_flex_mode"] is True
        assert check["effective_flex_mode"] is True
        assert check["document_path"].endswith(".md")
        assert check["document_revision"]
        assert readiness["inventory_freshness"]["from_cache"] is True


def test_inventory_failure_is_explicit_unknown_and_refresh_eligible(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _configured_task(root, "task_001")
    monkeypatch.setattr(
        "cascade.war_room.serialize.get_provider_inventory",
        lambda: (_ for _ in ()).throw(RuntimeError("secret upstream payload")),
    )
    _support_compatibility(monkeypatch)

    row = board_view_from_index(list_board(root), root=root)["tasks"]["1_backlog"][0]
    readiness = row["provider_readiness"]

    assert readiness["outcome"] == "transient"
    assert readiness["reason_code"] == "capability_unknown"
    assert readiness["inventory_freshness"]["stale"] is True
    assert readiness["inventory_freshness"]["age_seconds"] is None
    assert readiness["actions"]["refresh"] == {"eligible": True}
    assert "secret upstream payload" not in repr(readiness)


def test_epic_projection_keeps_every_failed_role_and_configuration_action(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    doc = read_doc("epic_001", root=root)
    roles = (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    doc.meta = replace(
        doc.meta,
        provider="codex",
        models={role: "retired-model" for role in roles},
        reasoning={role: "high" for role in roles},
        flex_mode=True,
    )
    write_doc(doc, root=root)
    monkeypatch.setattr(
        "cascade.war_room.serialize.get_provider_inventory",
        lambda: _inventory(model="model-a", from_cache=False),
    )
    _support_compatibility(monkeypatch)

    row = board_view_from_index(list_board(root), root=root)["epics"]["1_backlog"][0]
    readiness = row["provider_readiness"]

    assert readiness["outcome"] == "blocked"
    assert [check["role"] for check in readiness["checks"]] == list(roles)
    assert {check["reason_code"] for check in readiness["checks"]} == {
        "model_not_offered"
    }
    assert all(check["document_revision"] for check in readiness["checks"])
    assert readiness["actions"]["change_provider"] == {"eligible": True}
    assert readiness["actions"]["refresh"]["eligible"] is False


def test_inventory_refresh_reprojects_without_lifecycle_side_effects(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _configured_task(root, "task_001", status="active")
    stage = {"available": False}

    def discover(provider):
        if provider == "codex" and stage["available"]:
            return ProviderDiscoverySnapshot(
                "codex",
                True,
                (
                    DiscoveredModel(
                        "model-a",
                        "model-a",
                        reasoning=ReasoningCapability("medium", ("high",)),
                        supports_flex_mode=True,
                    ),
                ),
                supports_flex_mode=True,
            )
        return ProviderDiscoverySnapshot(provider, False, failure="not_authenticated")

    monkeypatch.setattr("cascade.agent.discovery.inventory.discover_provider", discover)
    monkeypatch.setattr(
        "cascade.feature.recovery.recovery_status", lambda *_args, **_kwargs: None
    )
    _support_compatibility(monkeypatch)

    before = board_view_from_index(list_board(root), root=root)["tasks"]["2_active"][0]
    assert before["provider_readiness"]["outcome"] == "transient"
    assert before["provider_readiness"]["actions"]["provider_setup"] == {
        "eligible": True
    }

    stage["available"] = True
    refreshed = fetch_brief_provider_inventory(root, force_refresh=True)
    after = board_view_from_index(list_board(root), root=root)["tasks"]["2_active"][0]

    assert refreshed["refresh"] == {"forced": True, "failed": False, "error": None}
    assert after["provider_readiness"]["outcome"] == "supported"
    assert after["provider_readiness"]["inventory_freshness"]["from_cache"] is True
    assert read_doc("task_001", root=root).meta.status == "active"
    assert not (root / ".cascade" / "provider_blockers.json").exists()


def test_cached_success_does_not_clear_durable_recovery_blocker(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _configured_task(root, "task_001", status="active")
    blocker_path = root / ".cascade" / "provider_blockers.json"
    blocker_path.parent.mkdir(exist_ok=True)
    blocker_path.write_text(
        json.dumps(
            {
                "version": 2,
                "blockers": {
                    "task_001": {
                        "work_id": "task_001",
                        "tier": "task",
                        "active": True,
                        "classification": "transient",
                        "reason_code": "provider_not_authenticated",
                        "affected_roles": ["swe"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cascade.war_room.serialize.get_provider_inventory",
        lambda: _inventory(model="model-a", from_cache=True),
    )
    monkeypatch.setattr(
        "cascade.feature.recovery.recovery_status", lambda *_args, **_kwargs: None
    )
    _support_compatibility(monkeypatch)

    row = board_view_from_index(list_board(root), root=root)["tasks"]["2_active"][0]

    assert row["provider_readiness"]["outcome"] == "supported"
    assert row["provider_recovery"]["active"] is True
    assert row["provider_recovery"]["diagnostics"]["outcome"] == "supported"
    assert row["provider_recovery"]["actions"]["retry"] == {"eligible": True}
    persisted = json.loads(blocker_path.read_text(encoding="utf-8"))
    assert persisted["blockers"]["task_001"]["active"] is True
