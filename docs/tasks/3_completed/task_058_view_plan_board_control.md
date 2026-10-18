---
id: task_058
title: View plan board control
tier: task
status: completed
parent: feat_012
children: []
depends_on:
  - task_057
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# View plan board control

## Parent Feature

[feat_012](../../features/3_completed/feat_012_plan_viewer.md) — Plan viewer (View plan).

## Depends on

- [task_057](../../tasks/3_completed/task_057_plan_markdown_mermaid.md) — markdown and Mermaid render

## Acceptance criteria

- **`cascade/war_room/static/war_room.js`** — in `buildRow` for **all three tiers** (`epics`, `features`, `tasks`) and **all columns** (`1_backlog`, `2_active`, `3_completed`):
  - Append a **View plan** control in `.board-row-actions` (same button style as existing `actionButton` helpers).
  - Click navigates to **`/plan/{item.id}`** in the **same tab** (`window.location.assign` or `<a href>` with no `target=_blank`).
  - Click does **not** propagate to the row’s selection handler (feat_011): use `stopPropagation` on the button or keep it inside `.board-row-actions` with the existing `ev.target.closest(".board-row-actions")` guard on row click.
  - View plan does not call dispatch, attach, or merge APIs.
- **Visible under board lens**: every row that `renderBoard` draws gets the button, including lens-filtered features/tasks and cards in collapsed completed columns when expanded (when collapsed, cards are not in DOM — no change required).
- **`cascade/war_room/static/war_room.css`**: optional minor spacing if the action row wraps; no redesign.
- **Tests** — `tests/war_room/test_ui_render.py`:
  - Assert served War Room HTML or embedded JS bundle reference still loads `war_room.js` (existing markers).
  - Add assertion that `war_room.js` source (read from disk in test) contains the string `View plan` and `/plan/` (stable contract).
- **Manual check** (document in task PR): open War Room, click View plan on a known epic → plan page shows rendered body per task_057.

## Files likely touched

- `cascade/war_room/static/war_room.js`
- `cascade/war_room/static/war_room.css` (optional)
- `tests/war_room/test_ui_render.py`

## Implementation notes

Place the View plan button after tier-specific actions or consistently as the last action — pick one order and keep it for all tiers. Do not open JSON `/api/doc/{id}` in the browser from the board; always use `/plan/{id}`. Toast links may stay on `/api/doc/` in v1 (feat_012 risk note).

## Skills

_(none)_

## Test plan

```bash
pytest tests/war_room/test_ui_render.py tests/war_room/test_plan_viewer.py
```

## Out of scope

- Changing toast `link` targets to `/plan/`.
- Keyboard shortcuts or context menus.
- Opening plan view in a new tab (explicitly same-tab in feat_012).

## Decision log

_(empty)_
