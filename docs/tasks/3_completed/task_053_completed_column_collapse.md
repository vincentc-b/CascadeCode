---
id: task_053
title: Completed column collapse
tier: task
status: completed
parent: feat_011
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# Completed column collapse

## Parent Feature

[feat_011](../../features/3_completed/feat_011_board_focus_and_collapse.md) — Board focus and collapse.

## Depends on

_(none)_

## Acceptance criteria

- **`BoardFocus.completed_collapsed`** lives in session state alongside future lens fields (same object shape as feat_011): defaults `epics: false`, `features: true`, `tasks: true`.
- **`cascade/war_room/templates/war_room.html`**: each tier's **`3_completed`** column header includes a dedicated collapse control (not the card row). Backlog and **`2_active`** columns have no collapse control.
- **`cascade/war_room/static/war_room.css`**: collapsed completed columns hide card bodies but show a **count** of cards in that column **after** any focus filter is applied (when task_054/055 land, counts must still use the visible set; until then, visible set equals full column).
- **`cascade/war_room/static/war_room.js`**: `renderBoard(view)` (or a small helper it calls) respects `completed_collapsed[tier]` for `3_completed` only — cards are not appended when collapsed; count UI updates on each render/refresh.
- **Pure helpers** in **`cascade/war_room/static/board_focus.js`** (new): at minimum `defaultBoardFocus()`, `toggleCompletedCollapsed(focus, tier)`, and `countVisibleInColumn(visibleView, tier, column)` (or equivalent names) exportable for tests (`globalThis.BoardFocus` in browser; `module.exports` / `export` when run under Node). No duplicate Python implementation of collapse logic.
- Collapse controls do **not** fire on card **action** button clicks (Dispatch, Attach, Merge, etc.). Clicking a row/card does not toggle collapse.
- **No API changes**: `GET /api/board` unchanged; `cascade/war_room/serialize.py` untouched unless a unrelated bug is found.
- **Tests**: `tests/war_room/test_ui_render.py` (or sibling) asserts HTML includes collapse affordances for completed columns (stable `data-*` or class markers documented in the test). `tests/war_room/test_board_focus.py` runs `tests/war_room/board_focus_collapse_cases.mjs` via **`node`** subprocess when `node` is on `PATH` (otherwise `pytest.skip`); cases cover defaults and toggle behavior for `completed_collapsed`.

## Files likely touched

- `cascade/war_room/templates/war_room.html`
- `cascade/war_room/static/war_room.css`
- `cascade/war_room/static/war_room.js` (`renderBoard`, column render path)
- `cascade/war_room/static/board_focus.js` (new — collapse slice of `BoardFocus`)
- `tests/war_room/test_ui_render.py`
- `tests/war_room/test_board_focus.py` (new)
- `tests/war_room/board_focus_collapse_cases.mjs` (new)

## Implementation notes

Load `board_focus.js` before `war_room.js` in the template. Keep `attachedGraphId`, `focusGraphId`, and attach/detach flows in `war_room.js` unchanged — collapse is orthogonal to chat attach. Session-only state: in-memory variable reset on full page refresh is acceptable. When integrating with epic/feature lens later, always compute counts from the **filtered** view passed into the column renderer, not from raw `view[tier][col].length` before lens.

## Skills

_(none)_

## Test plan

```bash
pytest tests/war_room/test_board_focus.py tests/war_room/test_ui_render.py
```

(Node required for `test_board_focus.py` case runner; install Node locally or in CI if tests skip.)

## Out of scope

- Epic or feature lens filtering (task_054, task_055).
- Card click selection styling or toggling `selected_epic_id` / `selected_feature_id`.
- Persisting collapse to server, git, or `localStorage`.
- Changing `GET /api/board` or board item shape in `serialize.py` (parent field already present on items).

## Decision log

_(empty)_
