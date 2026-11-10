---
id: task_023_002_001
title: Add durable per-epic backlog priority and guarded reorder service
tier: task
status: completed
parent: feat_023_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4d3aaf584c9b83597753dfb597dbf1cf0cc15eb9
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add durable per-epic backlog priority and guarded reorder service

## Parent Feature

[feat_023_002](../../features/2_active/feat_023_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the shared domain state for canonical backlog-feature order, keyed by epic and feature ID.

Scope:
- Choose the smallest persistence format consistent with existing War Room mutation/storage guards; it must survive process restarts and be shared across clients.
- Provide an atomic reorder operation with an explicit concurrency token/version.
- Validate that the submitted order contains exactly the current backlog peers for one epic; reject stale tokens, duplicates, unknown IDs, cross-epic IDs, and non-backlog members without changing stored state.
- Reconcile lifecycle changes: append newly created backlog features after ranked peers, and ignore/compact departed, dispatched, or removed features on read.
- Keep dependency, readiness, execution-cap, plan-approval, and dispatch behavior unchanged.

Verification:
- Add focused service-level tests for persistence/reload, append/compaction, accepted reorder, and rejected stale/invalid writes.
- Prefer existing integration seams and real storage over mock-heavy unit coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
