---
id: task_028_002_002
title: Reconstruct and refresh implementation-review state
tier: task
status: completed
parent: feat_028_002
children: []
depends_on:
- task_028_002_001
owners:
- swe
skills: []
parent_rev: e6837e5c90bfffb1a5a847109c6a4c7f90e03950
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Reconstruct and refresh implementation-review state

## Parent Feature

[feat_028_002](../../features/2_active/feat_028_002.md)

## Depends on

- task_028_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement durable review lookup and refresh so pending epic close state is reconstructed after restart from the stored snapshot and current forge review. Translate failed or missing forge lookups into the structured actionable blocker state defined by the persisted model, without creating a replacement review.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
