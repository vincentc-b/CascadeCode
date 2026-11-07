---
id: task_037_001_005
title: Migrate selection consumers and verify preview/execution parity
tier: task
status: completed
parent: feat_037_001
children: []
depends_on:
- task_037_001_004
owners:
- swe
skills: []
parent_rev: 272318a21e2b769ed35a2db841f6b233bee7bbff
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Migrate selection consumers and verify preview/execution parity

## Parent Feature

[feat_037_001](../../features/2_active/feat_037_001.md)

## Depends on

- task_037_001_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Migrate existing brief validation, dispatch/preflight, and execution selection consumers to the shared result/selection contract without introducing a second status store or evaluator. Keep behavior within feat_037_001 shared-contract scope; downstream lifecycle gates, incidents, Flex waiver, and War Room UI belong to later features. Add one representative integration test showing preview and execution receive identical effective provider/model/reasoning/Flex selections and fingerprint, plus focused compatibility checks for existing response fields. Run the relevant existing preflight/discovery/stack tests; avoid duplicating the full failure matrix at each boundary.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
