---
id: task_030_002_002
title: Implement journaled active-to-backlog transaction
tier: task
status: completed
parent: feat_030_002
children: []
depends_on:
- task_030_002_001
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
# Implement journaled active-to-backlog transaction

## Parent Feature

[feat_030_002](../../features/2_active/feat_030_002.md)

## Depends on

- task_030_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Implement the ordered, durable active-to-backlog mutation as a replay-safe journaled transaction.

## Scope
- Persist transition intent and durable step progress before/after each irreversible boundary.
- Preserve active-run artifacts.
- Restore the source brief as the backlog representation.
- Remove the active pointer and invalidate stale run identity/state.
- Enforce Git safety checks and refuse unsafe repository states.
- Ensure the operation never mutates operator trunk.

## Acceptance criteria
- Every durable boundary is represented in the journal and can be distinguished after restart.
- Successful completion preserves required run artifacts, restores the source brief, removes the active pointer, and makes stale runs unusable.
- Unsafe Git state fails safely without operator-trunk mutation.
- Repeating the same request does not duplicate or corrupt artifacts.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
