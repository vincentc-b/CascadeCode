"""HTTP boundary coverage for human provider recovery actions."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.agent.execution_preflight import (
    ProviderSelection,
    provider_blocker,
    recheck_provider_capability,
)
from cascade.board.store import list_board, read_doc, write_doc
from cascade.epic.lifecycle_gate import LifecycleGate
from cascade.task.checkpoint import thread_config
from cascade.task.graph import ensure_task_graph
from cascade.provider_recovery_command import ProviderRecoveryCommandResult
from cascade.war_room.provider_routes import try_handle_provider_post
from cascade.war_room.serialize import board_view_from_index
from tests.support import add_doc, make_repo


class _Handler:
    def __init__(self, root: Path, path: str) -> None:
        self.server = SimpleNamespace(root=root)
        self.path = path
        self.responses: list[tuple[int, dict]] = []

    def _json_response(self, status: int, payload: dict) -> None:
        self.responses.append((int(status), payload))

    def _json_error(self, status: int, message: str) -> None:
        self._json_response(status, {"error": message})


def _blocked_task(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_002",
        title="Sibling",
        tier="task",
        status="active",
        parent="feat_001",
    )
    (root / ".cascade").mkdir(exist_ok=True)
    (root / ".cascade" / "provider_blockers.json").write_text(
        json.dumps(
            {
                "version": 1,
                "blockers": {
                    "task_001": {"active": True, "classification": "transient"},
                    "task_002": {"active": True, "classification": "transient"},
                },
            },
        ),
        encoding="utf-8",
    )
    return root, "task_001"


def _inventory(*, model: str | None) -> ProviderInventoryResult:
    """Use the production capability contract while keeping the provider external."""

    providers = () if model is None else (
        ProviderInventoryItem(
            "codex", "Codex", (DiscoveredModel(id=model, display_name=model),),
        ),
    )
    failures = () if model is not None else (
        ProviderInventoryFailure("codex", "api_error", "credential=never-persist"),
    )
    return ProviderInventoryResult(
        providers=providers,
        failures=failures,
        freshness=InventoryFreshness(False, 1.0, 1.0, 1.0),
    )


def test_change_is_human_authorized_and_clears_only_recovered_blocker(
    tmp_path, monkeypatch
) -> None:
    root, work_id = _blocked_task(tmp_path)
    observed = {}

    def recover(item, request, **kwargs):
        observed.update(item=item, request=request, **kwargs)
        return ProviderRecoveryCommandResult(
            True, item, "fresh_role_turn", "checkpoint_pins_replaced"
        )

    monkeypatch.setattr(
        "cascade.war_room.provider_routes.recover_active_item_provider_command", recover
    )
    handler = _Handler(root, f"/api/provider-recovery/{work_id}/change")

    assert try_handle_provider_post(
        handler, {"provider": "codex", "models": {"swe": "model-a"}}
    )

    assert handler.responses == [
        (
            200,
            {
                "ok": True,
                "work_id": work_id,
                "disposition": "fresh_role_turn",
                "reason": "checkpoint_pins_replaced",
                "idempotent": False,
            },
        )
    ]
    assert observed["actor"] == "human"
    assert observed["request"].provider == "codex"
    blockers = json.loads(
        (root / ".cascade" / "provider_blockers.json").read_text(encoding="utf-8")
    )["blockers"]
    assert blockers[work_id]["active"] is False
    assert blockers["task_002"]["active"] is True


def test_retry_reuses_persisted_selection_after_credentials_are_restored(
    tmp_path, monkeypatch
) -> None:
    root, work_id = _blocked_task(tmp_path)
    doc = read_doc(work_id, root=root)
    doc.meta = replace(doc.meta, provider="codex", models={"swe": "model-a"})
    write_doc(doc, root=root)
    requests = []
    monkeypatch.setattr(
        "cascade.war_room.provider_routes.recover_active_item_provider_command",
        lambda _id, request, **_kwargs: (
            requests.append(request)
            or ProviderRecoveryCommandResult(
                True, _id, "resume_compatible", "checkpoint_pins_unchanged"
            )
        ),
    )
    handler = _Handler(root, f"/api/provider-recovery/{work_id}/retry")

    try_handle_provider_post(handler, {})

    assert handler.responses[0][0] == 200
    assert requests[0].provider == "codex"
    assert requests[0].models == {"swe": "model-a"}


def test_refusal_or_concurrent_turn_does_not_clear_blocker(
    tmp_path, monkeypatch
) -> None:
    root, work_id = _blocked_task(tmp_path)
    monkeypatch.setattr(
        "cascade.war_room.provider_routes.recover_active_item_provider_command",
        lambda item, _request, **_kwargs: ProviderRecoveryCommandResult(
            False,
            item,
            reason="The active turn did not quiesce; no selection was changed.",
            error_code="lifecycle_busy",
        ),
    )
    handler = _Handler(root, f"/api/provider-recovery/{work_id}/change")

    try_handle_provider_post(
        handler, {"provider": "codex", "models": {"swe": "model-a"}}
    )

    assert handler.responses[0][0] == 409
    assert handler.responses[0][1]["error_code"] == "lifecycle_busy"
    blockers = json.loads(
        (root / ".cascade" / "provider_blockers.json").read_text(encoding="utf-8")
    )["blockers"]
    assert blockers[work_id]["active"] is True


def test_post_start_provider_loss_survives_restart_and_retry_recovers_only_target(
    tmp_path, monkeypatch
) -> None:
    """Exercise the user-visible journey across the durable/API boundaries.

    The individual engine tests cover all tiers and dirty Task worktrees.  This
    journey instead proves their common public path: a post-start loss creates
    a safe durable blocker, a restarted board projects it, and restoring the
    provider lets Retry replace stale pins without touching a sibling.
    """

    root, work_id = _blocked_task(tmp_path)
    doc = read_doc(work_id, root=root)
    doc.meta = replace(doc.meta, provider="codex", models={"swe": "model-a"})
    write_doc(doc, root=root)
    graph = ensure_task_graph(work_id, root=root, feature_id="feat_001")
    graph.update_state(thread_config(work_id), {
        "provider_ids": {"swe": "codex"},
        "model_ids": {"swe": "stale-model"},
        "model_id": "stale-model",
    })
    monkeypatch.setattr(
        "cascade.agent.execution_preflight.refresh_provider_inventory",
        lambda: _inventory(model=None),
    )

    failed = recheck_provider_capability(
        work_id,
        tier="task",
        selections=(ProviderSelection("swe", "codex", "model-a"),),
        root=root,
    )

    assert not failed.supported
    # A new read is the same process-independent path used after a restart.
    restarted = provider_blocker(work_id, root=root)
    assert restarted is not None
    assert "never-persist" not in repr(restarted)
    monkeypatch.setattr(
        "cascade.feature.recovery.recovery_status", lambda *_args, **_kwargs: None
    )
    board = board_view_from_index(list_board(root), root=root)
    row = board["tasks"]["2_active"][0]
    assert row["provider_recovery"]["reason_code"] == "provider_unavailable"
    assert row["provider_recovery"]["actions"]["retry"] == {"eligible": True}
    assert row["provider_recovery"]["actions"]["provider_setup"] == {"eligible": True}
    assert row["provider_recovery"]["actions"]["return_to_backlog"]["reason_code"] == "not_epic"

    monkeypatch.setattr(
        "cascade.provider_recovery.refresh_provider_inventory",
        lambda: _inventory(model="model-a"),
    )
    monkeypatch.setattr("cascade.provider_recovery_command._kickoff", lambda _reason: None)
    handler = _Handler(root, f"/api/provider-recovery/{work_id}/retry")

    assert try_handle_provider_post(handler, {})
    assert handler.responses[0][0] == 200
    assert provider_blocker(work_id, root=root) is None
    pins = graph.get_state(thread_config(work_id)).values
    assert pins["model_ids"]["swe"] == "model-a"
    assert pins["model_id"] is None
    sibling = provider_blocker("task_002", root=root)
    assert sibling is not None and sibling["active"] is True


def test_retry_refuses_a_non_stoppable_turn_without_replacing_stale_pins(
    tmp_path, monkeypatch
) -> None:
    root, work_id = _blocked_task(tmp_path)
    doc = read_doc(work_id, root=root)
    doc.meta = replace(doc.meta, provider="codex", models={"swe": "model-a"})
    write_doc(doc, root=root)
    gate = LifecycleGate()
    monkeypatch.setattr("cascade.provider_recovery_command.lifecycle_gate", lambda: gate)
    monkeypatch.setattr(
        "cascade.provider_recovery.refresh_provider_inventory",
        lambda: _inventory(model="model-a"),
    )
    handler = _Handler(root, f"/api/provider-recovery/{work_id}/retry")

    with gate.turn(work_id):
        assert try_handle_provider_post(handler, {})

    assert handler.responses[0][0] == 409
    assert handler.responses[0][1]["error_code"] == "lifecycle_busy"
    assert provider_blocker(work_id, root=root) is not None
    assert read_doc(work_id, root=root).meta.models == {"swe": "model-a"}
