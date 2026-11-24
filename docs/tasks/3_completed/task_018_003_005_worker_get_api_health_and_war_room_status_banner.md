---
id: task_018_003_005
title: Worker GET /api/health and War Room status banner
tier: task
status: completed
parent: feat_018_003
children: []
depends_on:
- task_018_003_001
owners:
- swe
skills: []
parent_rev: a650ec93757565beabb62a80700efd2d29539047
created: '2026-10-23'
updated: '2026-10-23'
---
# Worker GET /api/health and War Room status banner

## Parent Feature

[feat_018_003](../../features/2_active/feat_018_003.md)

## Depends on

- task_018_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

- Worker route `GET /api/health` returns the parsed `supervisor_status.json`, using the same reader as task_018_003_001. It must stay answerable while draining (not a write, so it is not 503'd).
- War Room polls `/api/health` and shows a banner whenever `state != serving` or `trunk_lock_warning` is set, with state, last error message, and next action.

Tests: assert the health payload inside integration tests (a) and (b) instead of writing separate UI tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
