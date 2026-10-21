---
id: task_006
title: Add focused integration coverage for completion rollup and recovery
tier: task
status: completed
parent: feat_002
children: []
depends_on:
- task_005
owners:
- swe
skills: []
parent_rev: 5e9c28b830c389e515523846889c1d866fe27c75
created: '2026-10-21'
updated: '2026-10-21'
---
# Add focused integration coverage for completion rollup and recovery

## Parent Feature

[feat_002](../../features/2_active/feat_002.md)

## Depends on

- task_005

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration tests covering: all tasks done with an open merge request; both task/MR completion orderings; automatic epic completion after its last child; persisted incomplete follow-up children blocking rollup; unaccepted suggestions not blocking rollup; repeated reconciliation; and restart recovery. Avoid redundant low-level tests already exercised by these scenarios.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
