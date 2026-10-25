---
id: task_015_002_002
title: Verify planning readiness and stale approval handling
tier: task
status: completed
parent: feat_015_002
children: []
depends_on:
- task_015_002_001
owners:
- swe
skills: []
parent_rev: e5c158163561b8cca5ee4a668f6ee14a9a0b2936
created: '2026-10-24'
updated: '2026-10-24'
---
# Verify planning readiness and stale approval handling

## Parent Feature

[feat_015_002](../../features/2_active/feat_015_002.md)

## Depends on

- task_015_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add one high-signal UI integration test that covers the disabled approval reason, partial sign-off remaining blocked, and the transition from planning to ready after both current-revision sign-offs. Extend coverage of the existing approval error path so a stale-client server rejection remains visibly unsuccessful, retains the plan, exposes the actionable error, and triggers readiness refresh. Include assertions for semantic disabled/status information and reduced-motion-safe behavior where practical without duplicating lower-level coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
