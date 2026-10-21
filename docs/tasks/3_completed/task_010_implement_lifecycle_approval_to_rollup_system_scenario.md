---
id: task_010
title: Implement lifecycle approval-to-rollup system scenario
tier: task
status: completed
parent: feat_004
children: []
depends_on:
- task_009
owners:
- swe
skills: []
parent_rev: 2662c911ad6e18baeb2a1c31f1f08f58080f4490
created: '2026-10-21'
updated: '2026-10-21'
---
# Implement lifecycle approval-to-rollup system scenario

## Parent Feature

[feat_004](../../features/2_active/feat_004.md)

## Depends on

- task_009

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Using the disposable setup and existing public lifecycle entry points, implement one end-to-end browser/system scenario covering: approval, dependency gating, exactly-once dispatch of ready work, task/MR ordering, completion blocked by an open MR, merge-enabled feature and epic rollup, and restart reconciliation.

Acceptance:
- Blocked work does not dispatch; ready work dispatches exactly once.
- An open merge request prevents completion.
- Merging enables feature and epic completion rollup.
- Simulated restart/reconciliation can be repeated without duplicate dispatch or corrupt state.
- Assertions are made at stable system boundaries; no redundant mock-heavy unit suite is added.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
