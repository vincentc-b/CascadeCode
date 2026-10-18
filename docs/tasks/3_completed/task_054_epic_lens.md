---
id: task_054
title: Epic lens
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

# Epic lens

## Parent Feature

[feat_011](../../features/3_completed/feat_011_board_focus_and_collapse.md) — Board focus and collapse.

## Depends on

_(none)_

## Acceptance criteria

- **`cascade/war_room/static/board_focus.js`**: pure functions derive the feature lens from full board JSON and `BoardFocus`, using each item's **`parent`** field (already on board payloads from `serialize.py` / `work_meta_to_dict`):
  - If `selected_epic_id` is set: `feature_parents = {selected_epic_id}` (single epic — **replaces** the active-epic set; no union with other `2_active` epics).
  - Else: `feature_parents = { id of every epic in view.epics["2_active"] }`.
  - **Visible features** = all feature items (all columns) whose `parent` is in `feature_parents`. Epics and tasks tiers are not filtered by this task.
- **Epic card click** on the board body (not action buttons): toggles `selected_epic_id`. If a feature is selected and its `parent` is not the newly selected epic, clear `selected_feature_id`.
- **Deselect**: clicking the same selected epic again clears `selected_epic_id`; if the selected feature's parent is no longer in the lens, clear `selected_feature_id` as well.
- A epic in **`1_backlog`** or **`3_completed`** may be selected and act as the lens (active column is only the default when nothing is selected).
- **Empty copy**: when `feature_parents` is empty (no epic in `2_active` and none selected), the features tier shows copy that **no epic is active or selected** — no feature cards rendered.
- **`renderBoard`** in **`war_room.js`** applies the lens to the features tier only; **`buildRow`** still receives real items for visible rows; action buttons unchanged.
- **No** filesystem moves, frontmatter edits, or **`GET /api/board`** filtering on the server.
- **Tests**: `tests/war_room/board_focus_epic_lens_cases.mjs` executed by **`tests/war_room/test_board_focus.py`** via `node` (skip if no `node`); cases cover active-epic default set, single-epic selection replacing the set, backlog/completed epic selection, feature parent clearing, and empty-state predicate. Extend **`test_ui_render.py`** only if needed for stable empty-state markers in HTML/embedded boot script.

## Files likely touched

- `cascade/war_room/static/board_focus.js`
- `cascade/war_room/static/war_room.js` (`renderBoard`, epic row click handlers)
- `cascade/war_room/static/war_room.css` (selected epic affordance, optional)
- `cascade/war_room/templates/war_room.html` (features-tier empty state container if not created dynamically)
- `tests/war_room/test_board_focus.py`
- `tests/war_room/board_focus_epic_lens_cases.mjs` (new)

## Implementation notes

Use board item `parent` from API — do not parse paths. Keep **`attach(graphId, kind)`** behavior intact; this task does not set selection on attach (task_055). Stop propagation on action button clicks so Dispatch / Activate / Attach / Close do not toggle epic selection. After `refreshBoard()`, re-apply lens from the same in-memory `BoardFocus`. Coordinate with task_053 so completed-column counts use lens-filtered feature lists.

## Skills

_(none)_

## Test plan

```bash
pytest tests/war_room/test_board_focus.py tests/war_room/test_ui_render.py
```

## Out of scope

- Task-tier lens or `selected_feature_id` on feature card click (task_055).
- Attaching a feature room updating board selection.
- Completed-column collapse (task_053) except consuming filtered counts if task_053 landed first.
- Persisting selection server-side or in git.

## Decision log

_(empty)_
