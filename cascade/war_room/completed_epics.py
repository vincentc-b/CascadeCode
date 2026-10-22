"""Completed-epic board presentation: display limit and repository history metadata."""

from __future__ import annotations

from pathlib import Path

from cascade.board.paths import column_dir
from cascade.tracking import completed_epics_history_url
from cascade.watchdog.config import completed_epic_display_limit

COMPLETED_EPICS_REPO_REL_PATH = column_dir("epic", "completed").as_posix()


def bound_completed_epic_rows(rows: list, *, limit: int) -> list:
    """Keep the newest rows according to the board's existing completed ordering."""

    if limit <= 0 or len(rows) <= limit:
        return list(rows)
    return rows[-limit:]


def completed_epics_board_settings(root: Path) -> dict[str, object]:
    limit = completed_epic_display_limit(root)
    url = completed_epics_history_url(root)
    return {
        "completed_epic_display_limit": limit,
        "completed_epics_history": {
            "path": COMPLETED_EPICS_REPO_REL_PATH,
            "url": url,
            "available": url is not None,
        },
    }
