---
id: task_043
title: Orphan detector
tier: task
status: completed
parent: feat_008
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Orphan detector

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

_(none — wave A)_

## Acceptance criteria

- `cascade/boss/orphans.py` implements **`detect_orphans(*, root) -> list[OrphanRecord]`** where each record includes at least: `kind` (one of `feature_without_parent`, `task_after_feature_completed`, `epic_with_active_child`), `work_id`, human-readable `message`, and a **`toast_payload`** dict compatible with `cascade/war_room/toasts.py` conventions (kind + id + body/message) for task_044 to surface.
- Detection rules (flag only, **no** `move_doc`, no auto-repair):
  - Feature with missing/empty `parent` or parent id not found on board.
  - Task whose parent feature is already in `3_completed` while the task is not completed.
  - Epic in `3_completed` with any child feature still in `1_backlog` or `2_active`.
- Pure function of current board index from `list_board`; safe to call frequently.
- `tests/boss/test_orphans.py` constructs minimal inconsistent boards and asserts expected records; clean board returns empty list.

## Files likely touched

- `cascade/boss/orphans.py`
- `tests/boss/test_orphans.py`

## Implementation notes

Extend `_API_KINDS` in toasts is **task_044** if new toast kinds are required; this task returns pre-shaped payload dicts using a documented kind string (e.g. `orphan`). Watchdog may call detector later; no loop edits here.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_orphans.py -q`

## Out of scope

- Repairing or moving orphaned docs
- HTTP routes and War Room orphan toasts (task_044)
- Boss dispatch or merge
