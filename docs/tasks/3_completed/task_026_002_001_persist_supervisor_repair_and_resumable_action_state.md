---
id: task_026_002_001
title: Persist supervisor repair and resumable-action state
tier: task
status: completed
parent: feat_026_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 5e447d7fbc064a7d92753a7a4f1c571ca38da425
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Persist supervisor repair and resumable-action state

## Parent Feature

[feat_026_002](../../features/2_active/feat_026_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add the minimal persisted state needed for the supervisor to distinguish mechanical lifecycle repair from an owned semantic decision and to resume the exact interrupted action.

## Scope

- Represent the interrupted action and its stable identity.
- Represent repairable mechanical preconditions and owned decision states.
- Preserve retry/resume data across supervisor restarts.
- Define idempotent state transitions so repeated supervision does not duplicate work.

## Acceptance

- An interrupted Task or queued merge can be reconstructed from persisted state.
- A recorded resolution points back to the same persisted action.
- The model does not grant Task workers new Git or forge permissions.
- Existing persisted records remain readable or have a focused migration path.

## Verification

Add focused persistence/transition tests at the lowest existing integration boundary; avoid redundant unit coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
