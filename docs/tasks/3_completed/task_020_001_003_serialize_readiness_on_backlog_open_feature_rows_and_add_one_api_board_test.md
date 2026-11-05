---
id: task_020_001_003
title: Serialize readiness on backlog/open feature rows and add one /api/board test
tier: task
status: completed
parent: feat_020_001
children: []
depends_on:
- task_020_001_002
owners:
- swe
skills: []
parent_rev: 10207c9b3e77020f0fcb2ffb93b501d817f96994
created: '2026-10-23'
updated: '2026-10-23'
---
# Serialize readiness on backlog/open feature rows and add one /api/board test

## Parent Feature

[feat_020_001](../../features/2_active/feat_020_001.md)

## Depends on

- task_020_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
In `cascade/war_room/serialize.py`, add `readiness: {"approved": bool, "blockers": [codes]}` to backlog/open feature rows only, computed by the shared readiness predicate.

## Test (single API-level test of `/api/board` or equivalent feature payload)
- Unapproved feature: `approved: false`, `not_approved` present (plus any other blockers, reported independently).
- Approved feature with an unmet dependency: `unmet_deps` with the dependency id.
- Ready feature: no blockers **and** it appears in `compute_boss_view().dispatchable_features` (proves no drift).

## Constraints
- Serialization is read-only (no `ensure_*`, writes, events, or lock).
- No per-gate unit tests.

## Done when
The new API test passes and existing tests pass unchanged.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
