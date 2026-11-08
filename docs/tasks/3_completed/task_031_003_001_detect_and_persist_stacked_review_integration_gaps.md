---
id: task_031_003_001
title: Detect and persist stacked-review integration gaps
tier: task
status: completed
parent: feat_031_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 81446f5c79c03457019990fb37fe0cbaad5dec43
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Detect and persist stacked-review integration gaps

## Parent Feature

[feat_031_003](../../features/2_active/feat_031_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement detection for an accepted Feature review whose PR targets a predecessor branch that has already integrated into the intended Epic branch. Persist the gap using the existing recovery-action model, route ownership to the Epic Team, and retain the original accepted-review provenance. Add focused coverage for classification and persistence; do not mark the Feature complete while the gap remains.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
