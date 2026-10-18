---
id: task_055
title: Feature lens
tier: task
status: completed
parent: feat_011
children: []
depends_on:
  - task_054
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# Feature lens

## Parent Feature

[feat_011](../../features/3_completed/feat_011_board_focus_and_collapse.md) — Board focus and collapse.

## Depends on

- [task_054](../../tasks/3_completed/task_054_epic_lens.md) — Epic lens (feature tier filtering and `selected_epic_id` rules)

## Acceptance criteria

- **`board_focus.js`**: given full board view + `BoardFocus`, **visible tasks** = tasks (all columns) with `parent === selected_feature_id`; when `selected_feature_id` is **null**, visible tasks = **none** (empty list, not all tasks).
- **Feature card click** (row/card, not action buttons): sets `selected_feature_id` and sets `selected_epic_id` to that feature's **`parent`**. Clicking the same selected feature again clears `selected_feature_id` (and clears `selected_epic_id` only if epic deselect rules from task_054 require it when the feature is cleared).
- **Tasks empty state** when no feature selected: copy tells the operator to **select a feature**; no task cards in any column.
- **`attach(item.id, "feature")`** in **`war_room.js`**: after successful attach, set board selection the same way as a feature card click (`selected_feature_id`, `selected_epic_id` from parent). Later epic/feature selection changes do **not** call **`detach()`** or clear `attachedGraphId`.
- **Selecting a card does not attach** — attach remains only via the Attach action button.
- **Action buttons** (Dispatch, Ask Boss, Merge, Activate, Close, Attach, etc.) do **not** toggle `selected_feature_id` or `selected_epic_id`. **Dispatch** on a visible feature leaves that feature selected after `refreshBoard()`.
- **`renderBoard`** applies epic lens (task_054) then task lens on the tasks tier; **`buildRow`** for tasks unchanged for branch label and Merge/Dispatch wiring.
- **No** `GET /api/board` filter; parent links on documents remain the only filter key.
- **Tests**: `tests/war_room/board_focus_feature_lens_cases.mjs` via **`node`** in `test_board_focus.py` (task parent matching, null feature → no tasks, deselect feature). **`test_ui_render.py`**: assert tasks empty-state marker when bootstrapped with no selection (substring/`data-*` test acceptable). Optional: source assertion that `attach()` calls shared selection helper without invoking `detach` on selection change.

## Files likely touched

- `cascade/war_room/static/board_focus.js`
- `cascade/war_room/static/war_room.js` (`renderBoard`, `buildRow` click targets, `attach`)
- `cascade/war_room/static/war_room.css` (selected feature affordance, tasks empty state)
- `cascade/war_room/templates/war_room.html`
- `tests/war_room/test_board_focus.py`
- `tests/war_room/board_focus_feature_lens_cases.mjs` (new)
- `tests/war_room/test_ui_render.py`

## Implementation notes

Extract shared **`applyFeatureSelection(focus, featureItem)`** (or equivalent) used by feature click and post-attach hook. Epic lens from task_054 must run first so a selected feature always sits inside the visible feature set. Chat: **`updateFocusUi`**, **`loadChat`**, and compose enablement stay tied to **`attachedGraphId`**, not board lens selection. Merge and dispatch paths must remain `apiPost` + `refreshBoard()` as today.

## Skills

_(none)_

## Test plan

```bash
pytest tests/war_room/test_board_focus.py tests/war_room/test_ui_render.py
```

## Out of scope

- Changing attach/detach API routes or sidecar behavior.
- Task-tier chat rooms.
- Persisting `BoardFocus` to disk or server.
- "Show all tasks" mode.

## Decision log

_(empty)_
