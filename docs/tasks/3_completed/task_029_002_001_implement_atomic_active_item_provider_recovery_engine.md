---
id: task_029_002_001
title: Implement atomic active-item provider recovery engine
tier: task
status: completed
parent: feat_029_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 396a9432ce1d4842233b6d4e705dfa5a2df2c272
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Implement atomic active-item provider recovery engine

## Parent Feature

[feat_029_002](../../features/2_active/feat_029_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the recovery transaction for an active Epic, Feature, or Task. Validate every affected role's provider/model selection plus reasoning, tier, and flex compatibility before mutation; atomically reconcile persisted selections and checkpoint pins; preserve plan, progress, worktree, dirty files, and all child selections. Produce an explicit outcome indicating whether the existing state is proven compatible and resumable or requires a fresh role turn. Include focused tests around validation failure and atomic rollback.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
