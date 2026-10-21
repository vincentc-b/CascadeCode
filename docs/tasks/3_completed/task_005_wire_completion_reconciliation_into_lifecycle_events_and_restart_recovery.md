---
id: task_005
title: Wire completion reconciliation into lifecycle events and restart recovery
tier: task
status: completed
parent: feat_002
children: []
depends_on:
- task_004
owners:
- swe
skills: []
parent_rev: 5e9c28b830c389e515523846889c1d866fe27c75
created: '2026-10-21'
updated: '2026-10-21'
---
# Wire completion reconciliation into lifecycle events and restart recovery

## Parent Feature

[feat_002](../../features/2_active/feat_002.md)

## Depends on

- task_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Invoke the shared completion reconciler after relevant task completion and feature merge transitions, and during startup/restart recovery. Preserve ordering independence so tasks-first and merge-first flows converge to the same durable state without repeated or duplicate completion effects.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
