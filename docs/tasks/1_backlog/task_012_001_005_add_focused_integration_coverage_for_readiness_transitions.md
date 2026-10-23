---
id: task_012_001_005
title: Add focused integration coverage for readiness transitions
tier: task
status: backlog
parent: feat_012_001
children: []
depends_on:
- task_012_001_004
owners:
- swe
skills: []
parent_rev: 9d6ccdd55c94ce1e0b55d83bfe4b4e806d48a511
created: '2026-10-23'
updated: '2026-10-23'
---
# Add focused integration coverage for readiness transitions

## Parent Feature

[feat_012_001](../../features/2_active/feat_012_001.md)

## Depends on

- task_012_001_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration coverage proving the HTTP endpoint can be live while automation is not ready, recovered work does not delay watchdog startup, readiness later becomes ready after successful supervision/reconciliation, degraded details are observable, and status reads have no lifecycle or dispatch side effects.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
