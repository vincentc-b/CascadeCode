---
id: task_038_001_002
title: Extract authoritative dependency evaluation shared by readiness and dispatch
tier: task
status: completed
parent: feat_038_001
children: []
depends_on:
- task_038_001_001
owners:
- swe
skills: []
parent_rev: 855508b1a1a61e62bb0531bb8252408dc830a4b1
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Extract authoritative dependency evaluation shared by readiness and dispatch

## Parent Feature

[feat_038_001](../../features/2_active/feat_038_001.md)

## Depends on

- task_038_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Reuse canonical tracking-root and merged-board resolution to evaluate declared dependencies; consolidate duplicated completion predicates in feature readiness, dispatch, and stacked dependency checks without changing their explicit review/stacked action restrictions. Completion requires status completed in 3_completed. Distinguish known incomplete, cancelled, and status/column mismatch from missing IDs and source failures; fail closed when the authoritative source cannot be established. Cover tracking-repository ownership, completed trunk precedence, empty lists, and source failure in focused board/dispatch integration tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
