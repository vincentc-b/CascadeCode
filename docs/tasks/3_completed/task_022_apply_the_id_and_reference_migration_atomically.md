---
id: task_022
title: Apply the ID and reference migration atomically
tier: task
status: completed
parent: feat_010
children: []
depends_on:
- task_021
owners:
- swe
skills: []
parent_rev: 46c0e93179972a8d425044686910ab46a630d00b
created: '2026-10-22'
updated: '2026-10-22'
---
# Apply the ID and reference migration atomically

## Parent Feature

[feat_010](../../features/2_active/feat_010.md)

## Depends on

- task_021

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Using the validated migration plan, implement the board-owned document/path and metadata/reference rewrites for backlog epics and their descendant features/tasks. Preserve content unrelated to identifiers, keep active/completed work unchanged, and provide all-or-nothing behavior: stage and validate the complete result before commit, with no partial board mutation on failure. Acceptance: every mapped ID and board-owned reference is updated consistently; collisions or write/validation failures leave the board unchanged.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
