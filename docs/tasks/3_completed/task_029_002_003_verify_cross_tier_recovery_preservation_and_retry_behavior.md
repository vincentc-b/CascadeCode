---
id: task_029_002_003
title: Verify cross-tier recovery preservation and retry behavior
tier: task
status: completed
parent: feat_029_002
children: []
depends_on:
- task_029_002_002
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
# Verify cross-tier recovery preservation and retry behavior

## Parent Feature

[feat_029_002](../../features/2_active/feat_029_002.md)

## Depends on

- task_029_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration or end-to-end coverage for the recovery command on Epic, Feature, and Task. Verify lifecycle serialization; full role/reasoning/tier/flex validation; atomic selection and checkpoint reconciliation; preservation of plan, progress, worktree, dirty files, and child selections; compatible-state resume; incompatible-state fresh-turn reconstruction; failure rollback; and idempotent retry. Avoid redundant lower-level tests already covered by the recovery-engine suite.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
