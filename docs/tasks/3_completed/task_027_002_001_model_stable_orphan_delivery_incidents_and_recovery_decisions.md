---
id: task_027_002_001
title: Model stable orphan-delivery incidents and recovery decisions
tier: task
status: completed
parent: feat_027_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e93ae4deb3969a60974ddf6a130d226e48b6c71f
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Model stable orphan-delivery incidents and recovery decisions

## Parent Feature

[feat_027_002](../../features/2_active/feat_027_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Under the Task lifecycle lock, add the shared state/decision model that derives a stable orphan-delivery incident from ownership, durable delivery evidence, checkpoint, pinned execution inputs, and Git state. Define explicit outcomes for live owner, matching validated commit, resumable execution, unsafe/missing state, and no-op replay. Keep derivation deterministic and side-effect free.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
