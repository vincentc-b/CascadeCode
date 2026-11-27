---
id: task_030_001_001
title: Implement shared fail-closed return eligibility evaluator
tier: task
status: completed
parent: feat_030_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2715132c95ec4be0166c0ef194500ff5e46d9bd4
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Implement shared fail-closed return eligibility evaluator

## Parent Feature

[feat_030_001](../../features/2_active/feat_030_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define the eligibility input/result contract and stable refusal reason codes; implement one fail-closed evaluator consumed by all later presentation and command paths. Add table-driven coverage for every eligibility predicate, including unknown/missing state.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
