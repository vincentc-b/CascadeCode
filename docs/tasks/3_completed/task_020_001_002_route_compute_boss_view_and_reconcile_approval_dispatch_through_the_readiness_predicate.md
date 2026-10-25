---
id: task_020_001_002
title: Route compute_boss_view and reconcile_approval_dispatch through the readiness predicate
tier: task
status: completed
parent: feat_020_001
children: []
depends_on:
- task_020_001_001
owners:
- swe
skills: []
parent_rev: 10207c9b3e77020f0fcb2ffb93b501d817f96994
created: '2026-10-23'
updated: '2026-10-23'
---
# Route compute_boss_view and reconcile_approval_dispatch through the readiness predicate

## Parent Feature

[feat_020_001](../../features/2_active/feat_020_001.md)

## Depends on

- task_020_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
Replace the duplicated gate checks in `cascade/boss/view.py::compute_boss_view` (feature filter) and `automation.reconcile_approval_dispatch` (active-parent-epic check) with calls to the predicate from task_020_001_001.

## Constraints
- `dispatchable_features` contains exactly the features whose predicate result has no blockers (approved and empty blockers).
- Reconcile enforces `epic_inactive`.
- No loosening relative to today's behavior; record any semantic difference via `record_decision` on feat_020_001.
- Read-only: no `ensure_*`, file writes, events, or dispatch lock from the view path.

## Done when
Existing boss-view and automation tests pass unchanged.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
