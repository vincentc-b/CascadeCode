---
id: task_042
title: Epic completion confirm
tier: task
status: completed
parent: feat_008
children: []
depends_on:
  - task_041
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Epic completion confirm

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

- task_041 — feature completion moves children to `3_completed` so epic-all-done detection is meaningful

## Acceptance criteria

- `cascade/boss/epic_complete.py` implements:
  - **`epic_ready_to_close(epic_id, *, root) -> bool`** (read-only): every child feature in `children` / board parent linkage is in `3_completed`; zero open comments with `author=human` on the epic doc.
  - **`surface_epic_close_prompt(epic_id, *, root) -> None`**: when `epic_ready_to_close` is true, append a **`Toast`** (or typed war_room event documented in module) with a stable payload shape task_044 can render as “Close epic?” (include `epic_id`, kind e.g. `epic_ready_to_close`); idempotent or debounced so repeated calls do not spam unbounded duplicates within one process (document chosen policy in tests).
  - **`confirm_epic_complete(epic_id, by: Principal, *, root) -> bool`**: if `by != "human"`, return `False`; else same gates as above; on success `move_doc(epic_id, "completed", ...)` and emit **`EpicCompleted`** `{ epic_id }` on dest `war_room` (and epic queue if applicable).
- **`on_feature_completed(feature_id, *, root)`** helper: locate parent epic; if all features complete, call `surface_epic_close_prompt`.
- `tests/boss/test_epic_complete.py`: human confirm succeeds when gates met; `by="boss"` refused; open human comment on epic blocks; non-human principal blocked; prompt helper fires when last feature completes.

## Files likely touched

- `cascade/boss/epic_complete.py`
- `tests/boss/test_epic_complete.py`

## Implementation notes

Human confirmation is intentional (DESIGN §12). task_044 adds War Room button posting to a route that calls `confirm_epic_complete(..., "human")`. Do not call `activate_epic` or Boss dispatch.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_epic_complete.py -q`

## Out of scope

- War Room UI button and POST route (task_044)
- Boss `confirm_epic_complete`
- Orphan repair
- Auto-close epic without human confirm
