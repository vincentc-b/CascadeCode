---
id: task_031_003_002
title: Create the reviewed reconciliation path to the Epic branch
tier: task
status: completed
parent: feat_031_003
children: []
depends_on:
- task_031_003_001
owners:
- swe
skills: []
parent_rev: dbbba3eb5092540d9e3130d9867ce61973abbfdb
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Create the reviewed reconciliation path to the Epic branch

## Parent Feature

[feat_031_003](../../features/2_active/feat_031_003.md)

## Depends on

- task_031_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Consume the persisted stacked-review integration-gap recovery action and produce an actionable follow-up review targeting the intended Epic branch. Preserve/link the originating review provenance, use the existing Epic Team recovery workflow, and make retries converge on the same reconciliation work rather than creating duplicate follow-ups. Cover the feat_029_002-style predecessor-already-integrated race through the point where accepted changes reach the Epic.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
