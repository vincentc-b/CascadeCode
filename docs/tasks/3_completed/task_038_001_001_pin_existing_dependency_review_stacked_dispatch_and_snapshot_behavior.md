---
id: task_038_001_001
title: Pin existing dependency, review, stacked dispatch, and snapshot behavior
tier: task
status: completed
parent: feat_038_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: ba6afab47e9b83c8c016943e4a5d32c76ebcff1a
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Pin existing dependency, review, stacked dispatch, and snapshot behavior

## Parent Feature

[feat_038_001](../../features/2_active/feat_038_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Before changing dependency evaluation, document the current review and stacked dispatch action gates and merged-board/cache snapshot semantics in the feature spec or decision log. Add focused compatibility tests that preserve these behaviors, including tracking-root ownership and completed trunk precedence. Keep these action gates explicit; dependency status alone must not authorize dispatch or review.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
