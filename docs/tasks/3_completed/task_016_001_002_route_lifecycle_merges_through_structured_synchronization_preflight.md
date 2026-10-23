---
id: task_016_001_002
title: Route lifecycle merges through structured synchronization preflight
tier: task
status: completed
parent: feat_016_001
children: []
depends_on:
- task_016_001_001
owners:
- swe
skills: []
parent_rev: 4a74bd1cf9be4a834804aa0f83cd7a10354e4857
created: '2026-10-23'
updated: '2026-10-23'
---
# Route lifecycle merges through structured synchronization preflight

## Parent Feature

[feat_016_001](../../features/2_active/feat_016_001.md)

## Depends on

- task_016_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Adopt the shared synchronization preflight and diagnostic contract in task integration, feature rollup, and epic promotion.

## Scope

- Route all three lifecycle merge paths through the shared lock, cleanliness checks, branch invariants, and typed failure mapping.
- Preserve lifecycle state and branch state whenever preflight or merge fails.
- Surface actionable structured reasons to callers without raw command output.
- Retain only the existing activation-created epic pointer automatic conflict resolution; do not broaden automatic conflict handling.
- Add no War Room controls.

## Acceptance

Task merge, feature rollup, and epic close use one contract, serialize against updates, preserve state on failure, and retain the sole documented pointer-conflict exception.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
