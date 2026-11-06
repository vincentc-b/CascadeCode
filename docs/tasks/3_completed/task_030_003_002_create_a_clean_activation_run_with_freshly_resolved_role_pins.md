---
id: task_030_003_002
title: Create a clean activation run with freshly resolved role pins
tier: task
status: completed
parent: feat_030_003
children: []
depends_on:
- task_030_003_001
owners:
- swe
skills: []
parent_rev: 4c64393c84c8ac70e80f8b7cc5854262e14ca799
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Create a clean activation run with freshly resolved role pins

## Parent Feature

[feat_030_003](../../features/2_active/feat_030_003.md)

## Depends on

- task_030_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Make activation after reviewed edits create a new run identity and resolve role provider/model pins from the newly reviewed configuration.

## Acceptance criteria

- Reactivation creates a fresh run identity rather than resuming an archived run.
- Archived checkpoints are ignored during the new activation.
- Role pins are freshly resolved from the reviewed provider/model configuration.
- Activation refuses when reviewed state or existing child work makes reactivation unsafe.
- Tests focus on the activation boundary and avoid redundant lower-level coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
