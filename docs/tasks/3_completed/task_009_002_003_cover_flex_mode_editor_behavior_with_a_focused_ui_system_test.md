---
id: task_009_002_003
title: Cover flex-mode editor behavior with a focused UI/system test
tier: task
status: completed
parent: feat_009_002
children: []
depends_on:
- task_009_002_002
owners:
- swe
skills: []
parent_rev: 5304ce52a61bad1ddab11ef34768677ae0b0a422
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
---
# Cover flex-mode editor behavior with a focused UI/system test

## Parent Feature

[feat_009_002](../../features/2_active/feat_009_002.md)

## Depends on

- task_009_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add one focused high-signal UI/system test covering capability-based visibility, default-on for a new brief, explicit opt-out saved and preserved after reopening, switching to an unsupported provider with value normalization, and returning to a capable provider. Assert submission uses the same persisted brief field consumed by execution; avoid redundant lower-level tests already exercised by this scenario.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
