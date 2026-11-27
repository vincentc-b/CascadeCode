---
id: task_035_001_002
title: Resolve review context and accountable team routing
tier: task
status: completed
parent: feat_035_001
children: []
depends_on:
- task_035_001_001
owners:
- swe
skills: []
parent_rev: 0459d70ab5b68e790d813b2440b0d5783f86bcae
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Resolve review context and accountable team routing

## Parent Feature

[feat_035_001](../../features/2_active/feat_035_001.md)

## Depends on

- task_035_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Resolve the open review, authorized refs, observed source SHA, worktree, owning scope, and exactly one accountable team for an admitted resolution action.

## Acceptance criteria

- Feature-owned reviews route to their Feature Team.
- Epic-owned and explicitly assigned child reviews route to the Epic Team.
- Cross-feature cases select one accountable owner only when unambiguous; otherwise they return a blocking result.
- Resolution exposes scoped read-only inspection data required by later safety checks.
- Routing and ambiguity cases have focused tests.

## Non-goals

No worktree edits, rebase, conflict resolution, push, or unrestricted shell access.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
