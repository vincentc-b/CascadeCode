---
id: task_004
title: Implement idempotent feature and epic completion reconciliation
tier: task
status: completed
parent: feat_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 5e9c28b830c389e515523846889c1d866fe27c75
created: '2026-10-21'
updated: '2026-10-21'
---
# Implement idempotent feature and epic completion reconciliation

## Parent Feature

[feat_002](../../features/2_active/feat_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the core reconciliation rules from persisted lifecycle state: a feature completes only when every task is complete and its merge request is merged; an epic completes only when every persisted child feature is complete. Persisted incomplete follow-up children must block epic completion, while unminted suggestions must have no effect. Ensure repeated evaluation produces no duplicate transitions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
