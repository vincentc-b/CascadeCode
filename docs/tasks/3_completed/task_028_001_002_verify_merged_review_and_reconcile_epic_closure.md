---
id: task_028_001_002
title: Verify merged review and reconcile epic closure
tier: task
status: completed
parent: feat_028_001
children: []
depends_on:
- task_028_001_001
owners:
- swe
skills: []
parent_rev: d8939ce0926a2e7a4cf0315ab36b7dbb7a8af79f
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Verify merged review and reconcile epic closure

## Parent Feature

[feat_028_001](../../features/2_active/feat_028_001.md)

## Depends on

- task_028_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Keep epic closure pending while the implementation review is open. After merge, verify on remote trunk that the review is merged and the epic document is completed, surface either failed verification as a blocker, then finalize closure idempotently without opening a terminal-only closeout review. Preserve the operator's product-trunk checkout.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
