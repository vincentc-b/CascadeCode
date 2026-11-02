---
id: task_030_003_003
title: Prove the Cursor-failure to Codex-reactivation journey end to end
tier: task
status: completed
parent: feat_030_003
children: []
depends_on:
- task_030_003_002
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
# Prove the Cursor-failure to Codex-reactivation journey end to end

## Parent Feature

[feat_030_003](../../features/2_active/feat_030_003.md)

## Depends on

- task_030_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add a high-signal epic_028 end-to-end scenario covering credential failure, reviewed provider/model correction, and clean Codex activation.

## Acceptance criteria

- The scenario begins with a Cursor credential failure.
- The Epic is restored and its provider/model selection is changed through the reviewed MR-backed path.
- Later activation uses Codex with a fresh run identity and freshly resolved role pins.
- The journey proves archived checkpoints are ignored.
- Negative cases prove refusal for already-reviewed and child-work-present states.
- The test validates the integrated user journey without duplicating implementation-level tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
