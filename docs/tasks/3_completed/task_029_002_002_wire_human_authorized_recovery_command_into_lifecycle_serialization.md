---
id: task_029_002_002
title: Wire human-authorized recovery command into lifecycle serialization
tier: task
status: completed
parent: feat_029_002
children: []
depends_on:
- task_029_002_001
owners:
- swe
skills: []
parent_rev: 396a9432ce1d4842233b6d4e705dfa5a2df2c272
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Wire human-authorized recovery command into lifecycle serialization

## Parent Feature

[feat_029_002](../../features/2_active/feat_029_002.md)

## Depends on

- task_029_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Expose one human-authorized recovery command for active Epic, Feature, and Task items. Serialize it with lifecycle activity, invoke the atomic recovery engine, reject concurrent or invalid recovery safely, and resume compatible state or reconstruct and dispatch a fresh role turn according to the engine outcome. Ensure retrying the same completed recovery is idempotent and does not alter child selections.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
