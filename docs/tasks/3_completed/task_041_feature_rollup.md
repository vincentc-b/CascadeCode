---
id: task_041
title: Feature rollup and closeout
tier: task
status: completed
parent: feat_008
children: []
depends_on:
  - task_040
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Feature rollup and closeout

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

- task_040 — stable `TaskMerged` event payload shape `{ task_id, branch, merge_sha }` (implementation may use board state without calling merge)

## Acceptance criteria

- `cascade/boss/rollup.py` implements:
  - **`write_closeout(feature_id, paragraph: str, *, root)`** — deterministic, non-LLM: ensures the Feature `.md` has a `## Closeout` section containing the given one-paragraph text (create or replace body under that heading); commits via existing `write_doc` / `save_doc` patterns; does not move columns by itself.
  - **`try_complete_feature(feature_id, *, root) -> bool`**: returns `False` without side effects when any gate fails; on success returns `True` after:
    - Every child task id listed on the feature (frontmatter `children` and/or tasks whose `parent` is this feature) is in `3_completed` with status `completed`.
    - Zero **open** comments with `author=human` on the feature doc (load sidecar via `cascade/comments/store.py` helpers / `_load_sidecar` pattern).
    - Closeout paragraph present (non-empty under `## Closeout`).
    - Then `move_doc(feature_id, "completed", ...)` and enqueue **`FeatureCompleted`** `{ feature_id }` to epic graph dest (parent epic id).
  - **`on_task_merged(task_id, *, root) -> None`**: resolve parent feature from board; call `try_complete_feature(parent_id)` (no-op if gates fail).
- `tests/boss/test_rollup.py`: all tasks completed + closeout + no open human comments → feature moves to `3_completed` and event emitted; open human comment → `False`; missing closeout → `False`; partial task completion → `False`; `on_task_merged` triggers completion when gates already satisfied.

## Files likely touched

- `cascade/boss/rollup.py`
- `tests/boss/test_rollup.py`

## Implementation notes

Feature Architect graph may call `write_closeout` later; this task only provides the function. Do not boot Feature graph or run LLM. Comment gate matches DESIGN §12 (any open human thread blocks completion; `blocking` flag is not required for the gate). task_044 wires `on_task_merged` after HTTP merge; this task only exports the helper.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_rollup.py -q`

## Out of scope

- Epic completion prompt (task_042)
- Boss dispatch or merge
- Notifying Feature Team LLM to author closeout prose automatically
- `server.py` / `loop.py` wiring
- Auto-merge, activate_epic, setting comment `blocking`
