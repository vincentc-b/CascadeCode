---
id: task_034_003_005
title: Journal promotions with lineage-scoped reservations
tier: task
status: completed
parent: feat_034_003
children: []
depends_on:
- task_034_003_001
- task_034_003_004
owners:
- swe
skills: []
parent_rev: 37a365b227ed51c9ab6f3e7792e5e547dfc6d8e0
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Journal promotions with lineage-scoped reservations

## Parent Feature

[feat_034_003](../../features/2_active/feat_034_003.md)

## Depends on

- task_034_003_001
- task_034_003_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Persist a promotion journal keyed by review-unit identity and exact approved revision tuple, recording expected code/docs destination heads, accepted-baseline generation, and observed merge results. Scope accepted architecture pointers to integration lineage, not a mutable project-wide head. Reserve under the owning lifecycle lock, release it for Git/render work, and compare reservation/generation/heads again before finalization. Make concurrent promotion conflicts visible without overwriting newer acceptance. Add focused race and restart-state checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
