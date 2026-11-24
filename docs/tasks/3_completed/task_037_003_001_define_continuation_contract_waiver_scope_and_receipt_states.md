---
id: task_037_003_001
title: Define continuation contract, waiver scope, and receipt states
tier: task
status: completed
parent: feat_037_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 88a65eaae5360287bf141f3033e71576f958dad4
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define continuation contract, waiver scope, and receipt states

## Parent Feature

[feat_037_003](../../features/2_active/feat_037_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Document in this feature's API contracts the original-action identity and revision/selection fingerprint; exact role scope, stamped-descendant inheritance, child-override precedence and invalidation rules; non-secret audit fields; and durable receipt states/transitions for authorization, retry handoff, completion, drift and ambiguous handoff. Specify the four supported original actions and their ordinary gate/replay entry points before any mutation or replay implementation. Record consequential choices in the decision log.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
