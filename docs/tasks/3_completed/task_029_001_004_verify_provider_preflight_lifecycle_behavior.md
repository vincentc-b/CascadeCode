---
id: task_029_001_004
title: Verify provider preflight lifecycle behavior
tier: task
status: completed
parent: feat_029_001
children: []
depends_on:
- task_029_001_002
- task_029_001_003
owners:
- swe
skills: []
parent_rev: 3049608aef9088d87a3b2c93216daf8df4ef1c6a
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Verify provider preflight lifecycle behavior

## Parent Feature

[feat_029_001](../../features/2_active/feat_029_001.md)

## Depends on

- task_029_001_002
- task_029_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration coverage for supported configuration, deterministic rejection, transient failure, restart-visible deduplication, and the no-worktree/no-checkpoint guarantee on failed early preflight. Confirm unrelated work remains unaffected; add lower-level tests only where integration coverage cannot exercise classification or persistence semantics.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
