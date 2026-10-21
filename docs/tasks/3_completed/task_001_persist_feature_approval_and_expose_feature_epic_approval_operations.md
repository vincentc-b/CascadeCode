---
id: task_001
title: Persist feature approval and expose feature/epic approval operations
tier: task
status: completed
parent: feat_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 27e2c98dfbed1a2c01d4a4bedd9d1077b5cf81f0
created: '2026-10-21'
updated: '2026-10-21'
---
# Persist feature approval and expose feature/epic approval operations

## Parent Feature

[feat_001](../../features/2_active/feat_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Add approval as durable per-feature state, independent of lifecycle status, using the existing board persistence path.

## Scope
- Add the minimal approval field/state to the existing feature representation and serialization.
- Add per-feature approval through the existing command/API surface.
- Add epic approval that atomically/idempotently approves the epic's current child features only.
- Ensure children created after epic approval remain unapproved.
- Preserve compatibility for existing persisted features by treating missing approval state as unapproved.

## Acceptance
- Repeating either approval operation has no additional effect.
- Epic approval snapshots current children; later-added children require explicit approval.
- No second approval store or alternate workflow is introduced.
- Add focused tests at the persistence/API boundary where they provide unique coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
