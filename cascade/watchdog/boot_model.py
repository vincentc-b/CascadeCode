"""War Room toast when boot or chat cannot resolve models (fail closed)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event


def toast_model_config_failure(work_id: str, reason: str, *, root: Path) -> None:
    """Append one war_room Toast; does not start or mutate graphs."""

    repo = Path(root).resolve()
    message = f"Model configuration failed for {work_id}: {reason}"
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "blocked",
                "id": work_id,
                "message": message,
                "body": message,
            },
            dest="war_room",
        ),
        root=repo,
    )
