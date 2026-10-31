---
id: task_027_001_002
title: Revalidate changed delivery evidence and make replay idempotent
tier: task
status: completed
parent: feat_027_001
children: []
depends_on:
- task_027_001_001
owners:
- swe
skills: []
parent_rev: 8cba6581131aba3a53994eb8900a7dda871d6be9
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Revalidate changed delivery evidence and make replay idempotent

## Parent Feature

[feat_027_001](../../features/2_active/feat_027_001.md)

## Depends on

- task_027_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Complete the delivery-boundary behavior for evidence changes and replay.

Scope:
- Re-run final validation when the deliverable SHA or Feature-base SHA changes.
- Prevent stale validation evidence from producing awaiting_merge or ready.
- Make replay/retry idempotent so the same validated evidence cannot enqueue duplicate merges or emit conflicting state transitions.
- Reuse the durable evidence and queue boundary introduced by task_027_001_001.

Acceptance:
- Commit or base changes invalidate prior evidence and require fresh validation.
- Replaying unchanged validated evidence produces at most one matching merge queue entry.
- Red validation never advances the Task to awaiting_merge or ready.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
