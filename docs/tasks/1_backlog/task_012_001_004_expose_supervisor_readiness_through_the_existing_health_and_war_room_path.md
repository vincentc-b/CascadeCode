---
id: task_012_001_004
title: Expose supervisor readiness through the existing health and War Room path
tier: task
status: backlog
parent: feat_012_001
children: []
depends_on:
- task_012_001_002
- task_012_001_003
owners:
- swe
skills: []
parent_rev: 90a67ca2f1c4b4ec021ec871c777492e8979bb7d
created: '2026-10-23'
updated: '2026-10-23'
---
# Expose supervisor readiness through the existing health and War Room path

## Parent Feature

[feat_012_001](../../features/2_active/feat_012_001.md)

## Depends on

- task_012_001_002
- task_012_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Surface the authoritative projection through the existing health/War Room status path. Return separate HTTP liveness and automation readiness plus startup phase, activity timestamps, and actionable degraded reasons; reads must not mutate lifecycle state or dispatch work.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
