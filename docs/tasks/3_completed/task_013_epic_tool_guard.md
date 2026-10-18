---
id: task_013
title: Epic tool guard and scoped docs
tier: task
status: completed
parent: feat_004
children: []
depends_on:
  - task_012
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-10
---

# Epic tool guard and scoped docs

## Parent Feature

[feat_004](../../features/3_completed/feat_004_epic_team.md) — Epic Team graph.

## Depends on

- task_012 (Epic graph scaffolding / shared types as applicable)

## Acceptance criteria

- `tool_guard(path, op, *, epic_id, root)` returns `True`/`False` only; never raises for a denied path.
- Write allowed: this epic's markdown file; new or owned feature files under `docs/features/1_backlog/` only.
- Write denied: `docs/tasks/**`, feature `2_active`/`3_completed`, other epics, column moves, queue/comment/amendment sidecars, paths outside `docs/`.
- Read allowed: this epic file; child features (`parent == epic_id`) in any feature column; amendment diff paths under `docs/epics/2_active/_amendments/**/*.md`.
- Read denied: tasks, unrelated features/epics, queue and comment sidecars.
- `epic_read_doc` / `epic_write_doc` enforce the guard; task tier always denied via `EpicToolDenied`.
- Scoped modules do not import `move_doc`, `dispatch_feature`, `dispatch_task`, or `activate_epic`.

## Files likely touched

- `cascade/epic/guard.py`
- `cascade/epic/scoped_docs.py`
- `tests/epic/test_guard.py`

## Implementation notes

Resolve the epic with `read_doc`; unknown or non-epic id → deny. Normalize paths under `root`. For writes to an existing backlog feature, require board path unchanged (no column move) and `parent == epic_id`. Prefer `EpicToolDenied` (subclass of `PermissionError`) in `guard.py` for scoped doc failures.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_guard.py -q`

## Out of scope

- LangGraph wiring, mint_feature, comment store
- Package `cascade/epic/__init__.py` exports (separate task)
