---
id: task_028_001_001
title: Stage epic completion on the implementation branch
tier: task
status: completed
parent: feat_028_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: fd8018d49955ce94b7b5b23de74307c19a54f196
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Stage epic completion on the implementation branch

## Parent Feature

[feat_028_001](../../features/2_active/feat_028_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement idempotent preparation that moves the epic plan to completed state on the implementation branch before the implementation review is opened. Preserve the required human review gate and do not mutate the operator's product-trunk checkout. Add focused coverage for first-run and repeated preparation behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
