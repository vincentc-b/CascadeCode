"""Optional War Room routes for feat_018_002 drain integration (subprocess install only)."""

from __future__ import annotations

import os
import time
from http import HTTPStatus
from pathlib import Path


def install() -> None:
    if not os.environ.get("CASCADE_DRAIN_INTEGRATION"):
        return

    from cascade.war_room.server import WarRoomRequestHandler

    def slow_write(handler, body: dict) -> None:
        root = handler.server.root
        started = Path(os.environ["CASCADE_DRAIN_SLOW_STARTED"])
        started.parent.mkdir(parents=True, exist_ok=True)
        started.write_text("started\n", encoding="utf-8")
        delay = float(os.environ.get("CASCADE_DRAIN_SLOW_SECONDS", "1.5"))
        time.sleep(delay)
        token = str(body.get("token", ""))
        done = root / ".cascade" / "drain_slow_write.done"
        done.parent.mkdir(parents=True, exist_ok=True)
        done.write_text(token + "\n", encoding="utf-8")
        handler._json_response(HTTPStatus.OK, {"ok": True, "token": token})

    WarRoomRequestHandler.register_post_route("/api/drain_test_slow_write", slow_write)
