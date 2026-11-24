---
id: task_022_002_001
title: Implement provenance-aware direct-report blockage propagation
tier: task
status: completed
parent: feat_022_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 404fe156773f0a2b39ef5ba640e96d34bc7e25f4
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Implement provenance-aware direct-report blockage propagation

## Parent Feature

[feat_022_002](../../features/2_active/feat_022_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the core propagation path for an unresolved direct-report blockage. Persist machine-readable monitoring provenance with the originating child ID and concise reason; transition the immediate supervisor through existing canonical state-transition APIs with optimistic/version checks only. Treat an equivalent concurrently-applied transition as success, and do not mutate terminal work. Keep the rule generic to a direct child/supervisor pair so it can be reused at task → feature and feature → epic boundaries. Add focused tests only where they provide signal beyond the lifecycle integration task.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
