---
id: task_030_001_003
title: Add War Room Epic-row return control
tier: task
status: completed
parent: feat_030_001
children: []
depends_on:
- task_030_001_001
- task_030_001_002
owners:
- swe
skills: []
parent_rev: 31fc2f4ce7bc59019dba554db3ec4802e9e955f3
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Add War Room Epic-row return control

## Parent Feature

[feat_030_001](../../features/2_active/feat_030_001.md)

## Depends on

- task_030_001_001
- task_030_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Expose the return action on the War Room Epic row using the API contract. Derive visibility, enabled state, and refusal presentation from the same shared eligibility result and surface actionable refusal feedback.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
