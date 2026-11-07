---
id: task_030_002_003
title: Add transition recovery and deduplicated audit emission
tier: task
status: completed
parent: feat_030_002
children: []
depends_on:
- task_030_002_002
owners:
- swe
skills: []
parent_rev: 3888fd3c4f3565ab9df90f66cbc88cd62f068782
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Add transition recovery and deduplicated audit emission

## Parent Feature

[feat_030_002](../../features/2_active/feat_030_002.md)

## Depends on

- task_030_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Recover incomplete journaled transitions and produce exactly one logical audit outcome across retries and restarts.

## Scope
- Detect and resume or finalize incomplete transitions from journal state.
- Make each transition step idempotent under repeated execution.
- Deduplicate success/failure audit emission using stable transition identity.
- Surface safe, actionable failure state when automatic recovery cannot proceed.

## Acceptance criteria
- Restart at any durable boundary converges to one valid final state or an explicit safe refusal.
- Concurrent and repeated requests converge without duplicate state changes.
- A completed logical transition emits one deduplicated audit record.
- Recovery never resurrects stale active runs or mutates operator trunk.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
