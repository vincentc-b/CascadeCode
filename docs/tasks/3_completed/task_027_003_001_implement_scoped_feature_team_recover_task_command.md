---
id: task_027_003_001
title: Implement scoped Feature Team recover_task command
tier: task
status: completed
parent: feat_027_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: ebaa4bba43f2a63bb0492a08d4cfe39d67b2ca90
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Implement scoped Feature Team recover_task command

## Parent Feature

[feat_027_003](../../features/2_active/feat_027_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add the Feature Team recover_task(task_id) entry point for direct child Tasks only. Enforce scope authorization, delegate to the shared supervisor recovery operation, return precise recovery outcomes, and make simultaneous tool-initiated and sweep-initiated recovery requests converge safely without duplicate recovery work. Keep the implementation scoped to the existing recovery primitive and outcome model.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
