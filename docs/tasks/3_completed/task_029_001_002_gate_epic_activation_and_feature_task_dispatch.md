---
id: task_029_001_002
title: Gate Epic activation and Feature/Task dispatch
tier: task
status: completed
parent: feat_029_001
children: []
depends_on:
- task_029_001_001
owners:
- swe
skills: []
parent_rev: 3049608aef9088d87a3b2c93216daf8df4ef1c6a
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Gate Epic activation and Feature/Task dispatch

## Parent Feature

[feat_029_001](../../features/2_active/feat_029_001.md)

## Depends on

- task_029_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Invoke the shared preflight before Epic activation and before Feature or Task dispatch. On failure, stop before creating worktrees, checkpoints, or other dispatch artifacts; preserve existing behavior for unrelated work and propagate the structured blocker outcome.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
