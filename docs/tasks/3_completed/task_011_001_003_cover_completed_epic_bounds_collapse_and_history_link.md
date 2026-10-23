---
id: task_011_001_003
title: Cover completed-epic bounds, collapse, and history link
tier: task
status: completed
parent: feat_011_001
children: []
depends_on:
- task_011_001_001
- task_011_001_002
owners:
- swe
skills: []
parent_rev: 8e840776999c1293244bb4d01903a6b3313098fb
created: '2026-10-22'
updated: '2026-10-22'
---
# Cover completed-epic bounds, collapse, and history link

## Parent Feature

[feat_011_001](../../features/2_active/feat_011_001.md)

## Depends on

- task_011_001_001
- task_011_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add focused, high-signal render/integration coverage for the completed-epics board behavior. Prove initial collapse; the default limit of 10; valid configured positive limits; fallback for missing, malformed, zero, and negative values; retention of newest rows according to existing ordering; unchanged row selection across expand/collapse; link visibility and resolution when repository metadata exists; and a visible disabled affordance plus successful board render when metadata is unavailable. Prefer extending existing board-level coverage over redundant low-level tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
