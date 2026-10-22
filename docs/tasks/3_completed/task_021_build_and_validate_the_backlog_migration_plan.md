---
id: task_021
title: Build and validate the backlog migration plan
tier: task
status: completed
parent: feat_010
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 46c0e93179972a8d425044686910ab46a630d00b
created: '2026-10-22'
updated: '2026-10-22'
---
# Build and validate the backlog migration plan

## Parent Feature

[feat_010](../../features/2_active/feat_010.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement discovery and preflight planning for backlog epic renumbering. Enumerate only backlog epics and all descendant features/tasks; assign collision-free hierarchical target IDs; build a complete old-to-new mapping; enumerate every board-owned path/reference that must change; and reject the operation before any mutation when an ID collision, malformed hierarchy, missing target, or out-of-scope active/completed work would be affected. Acceptance: planning is deterministic, makes no writes, preserves active/completed IDs, and returns actionable validation errors.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
