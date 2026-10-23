---
id: task_011_001_001
title: Add completed-epic display limit and bounded selection
tier: task
status: completed
parent: feat_011_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 8e840776999c1293244bb4d01903a6b3313098fb
created: '2026-10-22'
updated: '2026-10-22'
---
# Add completed-epic display limit and bounded selection

## Parent Feature

[feat_011_001](../../features/2_active/feat_011_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the project-level Cascade YAML setting for the completed-epic display limit. Accept valid positive values; default missing, malformed, or non-positive values to 10. Apply the resolved limit only after the existing completed-epic ordering so the newest completed epics are retained. Do not affect active or proposed epic lists. Expose the bounded completed rows and any existing repository metadata needed by the board without adding a new archive API or duplicate store.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
