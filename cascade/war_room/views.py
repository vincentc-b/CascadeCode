"""Server-rendered War Room home page (task_011)."""

from __future__ import annotations

from html import escape
from pathlib import Path
from string import Template

from cascade.board.store import list_board
from cascade.war_room.serialize import column_folder_for_meta

_DEFAULT_EPIC_FALLBACK = "epic_001"
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "war_room.html"
_PLAN_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "plan_viewer.html"
_BOSS_PANEL_MARKUP = (
    '<div id="boss-view-summary" class="boss-summary" aria-live="polite"></div>'
)


def default_epic_graph_id(*, root: Path) -> str:
    """Epic id for default Epic War Room chat focus.

    Uses the sole epic in ``2_active`` when exactly one exists; if several are
    active, picks the lexicographically smallest id; otherwise ``epic_001``.
    """

    board = list_board(root)
    active: list[str] = []
    for meta in board.by_id.values():
        if meta.tier != "epic":
            continue
        try:
            folder = column_folder_for_meta(meta, root=root)
        except ValueError:
            continue
        if folder == "2_active":
            active.append(meta.id)
    if len(active) == 1:
        return active[0]
    if active:
        return sorted(active)[0]
    return _DEFAULT_EPIC_FALLBACK


def render_plan_page(work_id: str) -> str:
    template = Template(_PLAN_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute(work_id=escape(work_id, quote=True))


def render_war_room_page(*, root: Path) -> str:
    epic_id = default_epic_graph_id(root=root)
    template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        epic_graph_id=escape(epic_id, quote=True),
        branch_label_example=escape("task_001", quote=True),
        boss_panel_markup=_BOSS_PANEL_MARKUP,
    )
