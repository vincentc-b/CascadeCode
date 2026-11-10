---
id: task_034_005_003
title: Enforce durable scoped change holds at lifecycle boundaries
tier: task
status: completed
parent: feat_034_005
children: []
depends_on:
- task_034_005_001
owners:
- swe
skills: []
parent_rev: 87aca2adc4b8a39f924d3bf8ade32a3d84523a73
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce durable scoped change holds at lifecycle boundaries

## Parent Feature

[feat_034_005](../../features/2_active/feat_034_005.md)

## Depends on

- task_034_005_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Persist material-request holds with affected work/subtree, boundary set, reason, owner and release evidence. Gate affected minting, dispatch, task integration, feature merge and closure under existing lifecycle locks; report actionable hold state. Preserve running task branches/results while preventing held integration; leave unrelated accepted siblings untouched. Release only after recorded decision and required revised review/approval tuple. Cover restart/replay and scoped resume through integrated gates.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
