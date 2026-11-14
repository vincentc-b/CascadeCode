---
id: task_031_001_002
title: Route first branch-action failure once to the owning team
tier: task
status: completed
parent: feat_031_001
children: []
depends_on:
- task_031_001_001
owners:
- swe
skills: []
parent_rev: 06fb458f1bce07a45b24b842e7dd211e5b95b307
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Route first branch-action failure once to the owning team

## Parent Feature

[feat_031_001](../../features/2_active/feat_031_001.md)

## Depends on

- task_031_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add one shared recovery boundary for operator and supervisor branch updates, Task-to-Feature merges, Feature-to-Epic merges, and Epic promotion/close merges. On the first unsuccessful action, durably capture evidence and enqueue exactly one investigation on the normal owning Feature or Epic Team queue. Make repeated attempts and restarts idempotent without losing approvals, provenance, or user files.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
