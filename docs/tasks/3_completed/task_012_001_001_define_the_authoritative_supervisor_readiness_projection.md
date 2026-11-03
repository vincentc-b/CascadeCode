---
id: task_012_001_001
title: Define the authoritative supervisor readiness projection
tier: task
status: completed
parent: feat_012_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 62f5f54326ee185ab5138dbe42eb7345273acd7e
created: '2026-10-23'
updated: '2026-10-23'
---
# Define the authoritative supervisor readiness projection

## Parent Feature

[feat_012_001](../../features/2_active/feat_012_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the read-only supervisor health/readiness data model and projection. Keep HTTP liveness distinct from automation readiness; represent startup phase, last successful watchdog and reconciliation timestamps, and actionable degraded reasons. Observation must have no lifecycle or dispatch side effects.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
