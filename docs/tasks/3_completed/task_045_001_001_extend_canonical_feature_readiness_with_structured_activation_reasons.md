---
id: task_045_001_001
title: Extend canonical feature readiness with structured activation reasons
tier: task
status: completed
parent: feat_045_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 73c1f1dfd50ebec0dc4ed3eedf638c836da9bdd2
created: '2026-11-12'
updated: '2026-11-12'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Extend canonical feature readiness with structured activation reasons

## Parent Feature

[feat_045_001](../../features/2_active/feat_045_001.md)

## Depends on

None.

## Acceptance criteria

- The canonical readiness result exposes version 1 structured reasons and satisfied prerequisites while retaining the existing `approved` and `blockers` fields.
- Every blocking sibling ID is reported, with active execution distinguished from pending review or merge.
- Approval, dependency, parent, review, and base states produce deterministic ordered reasons. Missing required evidence cannot produce a ready summary.
- Existing dispatch refusal behavior and read-only polling remain unchanged.

## Files likely touched

- cascade/feature/readiness.py
- cascade/stacked_dispatch.py
- Focused feature readiness and stacked dispatch tests

## Implementation notes

Implement the feature plan's version 1 Python explanation model and deterministic reason ordering in cascade/feature/readiness.py and cascade/stacked_dispatch.py. Retain all blocking sibling IDs, distinguish active execution from pending merge/review, represent approval/dependency/parent/review/base gate states and satisfied prerequisites, preserve approved/blockers and action-boundary refusal semantics. Keep polling read-only and avoid new expensive Git probes. Add focused canonical gate/readiness tests, including serial/stacked behavior and approved sibling-wait fixture.

## Skills

_(none)_

## Test plan

Run focused canonical readiness and dispatch tests covering serial and stacked sibling waits, approval and dependency gates, and a previously approved sibling-wait fixture. Preserve the existing uncommitted implementation in the Task worktree and finish it on the same branch.

## Out of scope

TBD.
