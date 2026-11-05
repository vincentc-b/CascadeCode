---
id: task_035_001_004
title: Add end-to-end admission and routing contract tests
tier: task
status: completed
parent: feat_035_001
children: []
depends_on:
- task_035_001_001
- task_035_001_002
- task_035_001_003
owners:
- swe
skills: []
parent_rev: 0459d70ab5b68e790d813b2440b0d5783f86bcae
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Add end-to-end admission and routing contract tests

## Parent Feature

[feat_035_001](../../features/2_active/feat_035_001.md)

## Depends on

- task_035_001_001
- task_035_001_002
- task_035_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add high-signal integration/API coverage proving the complete non-mutating resolution-action admission flow.

## Acceptance criteria

- Tests exercise both operator and epic_031 recovery entry paths through the same contract.
- Tests verify duplicate admission is idempotent.
- Tests verify Feature Team, Epic Team, explicitly assigned child, and ambiguous cross-feature routing.
- Tests verify authorization and representative rejection boundaries, including persisted checkpoint and resume details.
- Tests assert no mutation-capable operation is invoked for rejected or admitted actions in this feature.

## Test strategy

Prefer a compact integration/API matrix over redundant mock-heavy unit coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
