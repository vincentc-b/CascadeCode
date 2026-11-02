"""HTTP boundary coverage for human provider recovery actions."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from cascade.board.store import read_doc, write_doc
from cascade.provider_recovery_command import ProviderRecoveryCommandResult
from cascade.war_room.provider_routes import try_handle_provider_post
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
