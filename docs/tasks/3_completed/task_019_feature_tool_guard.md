---
id: task_019
title: Feature tool guard and path sandbox
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_018
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Feature tool guard and path sandbox

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_018 (feature graph id / registry exist; boot hook may register tools later)

## Acceptance criteria

- `tool_guard(path, op, *, feature_id, root)` in `cascade/feature/guard.py` returns `True`/`False` only; never raises for a denied path.
- `FeatureToolDenied` (subclass of `PermissionError`) defined alongside the guard for scoped doc layers to raise.
- **Write allowed:** this feature’s own `.md` under `docs/features/**`; new or owned task files under `docs/tasks/1_backlog/` with `parent == feature_id`; append to `docs/_comments/{feature_id}.jsonl` only (not other doc ids).
- **Write denied:** any `docs/epics/**` path; other features; tasks whose parent is not this feature; task paths under `2_active` or `3_completed`; column moves; `docs/_queue/**`; comment sidecars for other doc ids; paths outside `docs/`.
- **Read allowed:** own feature file; parent epic blob at paths resolved for read (scoped read layer enforces `parent_rev`); own backlog/active/completed tasks with `parent == feature_id`; own comment sidecar `docs/_comments/{feature_id}.jsonl`.
- **Read denied:** epic war-room chat sidecars (`docs/_war_room/**`), other features’ comments, unrelated epics/features/tasks, queue/amendment sidecars, task-tier docs not owned by this feature.
- Guard modules do not import `dispatch_feature`, `dispatch_task`, `activate_epic`, or `move_doc`.
- `tests/feature/test_guard.py` covers allow/deny matrix including comment sidecar ownership and dispatch path denial.

## Files likely touched

- `cascade/feature/guard.py`
- `tests/feature/test_guard.py`

## Implementation notes

Resolve the feature with `read_doc(feature_id)`; unknown or non-feature id → deny. Normalize paths under `root`; reject symlink escapes (mirror `cascade/epic/guard.py`). For writes to an existing owned task, require the board path stays under `1_backlog` (no column move). Comment sidecar paths use `{doc_id}` matching this feature’s id for feature-team writes; epic comment paths are out of scope here (epic guard still denies `_comments` — epic comment writes go through the shared comment store in task_023 with epic-specific entrypoints).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/feature/test_guard.py -q`

## Out of scope

- Scoped `read_doc` / `write_doc` wrappers (task_020)
- Comment JSON schema persistence and queue events (task_023)
- LangGraph node changes (task_018)
- `mint_task`, `record_decision`, war-room briefing (tasks task_021–task_024)
