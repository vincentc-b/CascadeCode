---
id: task_034_004_005
title: Enforce scoped semantic blocking at review and lifecycle gates
tier: task
status: completed
parent: feat_034_004
children: []
depends_on:
- task_034_004_003
owners:
- swe
skills: []
parent_rev: 0c8dcfce53514e313135add1f4c23d57f5e470a5
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce scoped semantic blocking at review and lifecycle gates

## Parent Feature

[feat_034_004](../../features/2_active/feat_034_004.md)

## Depends on

- task_034_004_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend Feature C's existing exact reviewed-tuple and revision gates with unresolved semantic blocking threads. Derive affected work IDs from explicit review-unit/comment IDs, ownership, citations, and dependent closure at each boundary: approval, affected mint/dispatch, integration, merge, and closure. Re-evaluate against the current board graph; report thread IDs, affected IDs, reason, and a visible fallback flag. If a narrower scope is ambiguous, hold only the owning feature/epic subtree. Preserve running branches, accepted work, and unrelated epics. An outdated open blocking anchor remains blocking until the existing authorized human resolution action succeeds; revision drift or pending/stale review units continue to follow C's gate. Add focused lifecycle tests proving affected work is held, unrelated work proceeds, and exact revision invalidation is enforced. Keep broader material-change routing and full tier authoring outside this task.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
