---
id: task_037_002_002
title: Gate parent approvals on effective downstream selections
tier: task
status: completed
parent: feat_037_002
children: []
depends_on:
- task_037_002_001
owners:
- swe
skills: []
parent_rev: 2e851f651db32f7ec9b7c1271242a2a803da4d39
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Gate parent approvals on effective downstream selections

## Parent Feature

[feat_037_002](../../features/2_active/feat_037_002.md)

## Depends on

- task_037_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Before Epic or Feature approval grants downstream authorization, evaluate the existing effective selections for every affected child and role with the shared evaluator and owning-worktree provenance. Reject invalid late overrides and stale or unresolved legacy selections without advancing approval/checkpoint state. Keep accepted approvals intact when later environment drift only blocks dispatch. Carry complete structured failure details through approval responses, including an approval-triggered reconciliation failure. Cover these paths in approval integration fixtures with fake inventory.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
