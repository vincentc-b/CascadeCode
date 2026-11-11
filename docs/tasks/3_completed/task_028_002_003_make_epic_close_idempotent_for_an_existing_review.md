---
id: task_028_002_003
title: Make epic Close idempotent for an existing review
tier: task
status: completed
parent: feat_028_002
children: []
depends_on:
- task_028_002_002
owners:
- swe
skills: []
parent_rev: e6837e5c90bfffb1a5a847109c6a4c7f90e03950
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Make epic Close idempotent for an existing review

## Parent Feature

[feat_028_002](../../features/2_active/feat_028_002.md)

## Depends on

- task_028_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Update the epic Close flow to consult persisted/reconstructed implementation-review state before forge creation. Repeated Close requests while a review exists must return the same review identity and current state, including blocker details, and must not create a duplicate review.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
