"""Durable human approvals for Epic plans."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.workspace.integration_worktree import merged_board
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event


def _path(root: Path) -> Path:
    return root / ".cascade" / "approvals.json"


def _read(root: Path) -> dict[str, object]:
    path = _path(root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def epic_plan_approved(epic_id: str, *, root: Path) -> bool:
    return epic_id in _read(resolve_root(root))


def approve_epic_plan(epic_id: str, *, root: Path) -> dict[str, object]:
    repo = resolve_root(root)
    board = merged_board(repo)
    epic = board.by_id.get(epic_id)
    if epic is None or epic.tier != "epic" or epic.path.parent.name != "2_active":
        raise ValueError("epic plan can only be approved while its team is active")
    children = sorted(
        meta.id for meta in board.by_id.values()
        if meta.tier == "feature" and meta.parent == epic_id
    )
    if not children:
        raise ValueError("epic plan has no feature plans to approve yet")
    state = _read(repo)
    if epic_id not in state:
        state[epic_id] = {
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "features": children,
        }
        path = _path(repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)
        for dest in (epic_id, "war_room"):
            append_event(
                dest,
                Event(
                    type="Toast" if dest == "war_room" else "EpicPlanApproved",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "kind": "epic_plan_approved",
                        "id": epic_id,
                        "epic_id": epic_id,
                        "features": children,
                        "message": f"Plan approved for {epic_id}; feature work will start automatically",
                    },
                    dest=dest,
                ),
                root=repo,
            )
    return {"ok": True, "epic_id": epic_id, "features": children}
