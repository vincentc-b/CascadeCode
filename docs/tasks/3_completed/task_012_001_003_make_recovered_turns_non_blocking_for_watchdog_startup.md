---
id: task_012_001_003
title: Make recovered turns non-blocking for watchdog startup
tier: task
status: completed
parent: feat_012_001
children: []
depends_on:
- task_012_001_001
owners:
- swe
skills: []
parent_rev: 0cedad81a73dc6079de09dd2851d65e1d117faf2
created: '2026-10-23'
updated: '2026-10-23'
---
# Make recovered turns non-blocking for watchdog startup

## Parent Feature

[feat_012_001](../../features/2_active/feat_012_001.md)

## Depends on

- task_012_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Start watchdog supervision without awaiting recovered model turns. Submit recovered turns through the established background worker mechanism and retain readiness/degraded-state reporting for recovery progress and failures.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
