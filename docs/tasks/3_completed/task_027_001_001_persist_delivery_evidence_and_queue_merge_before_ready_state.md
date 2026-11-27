---
id: task_027_001_001
title: Persist delivery evidence and queue merge before ready state
tier: task
status: completed
parent: feat_027_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4b2bbe8a62eba30e4c37e201b187e7d6717df167
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Persist delivery evidence and queue merge before ready state

## Parent Feature

[feat_027_001](../../features/2_active/feat_027_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the core durable Task delivery transition.

Scope:
- Record Task ID, deliverable SHA, and Feature-base SHA as the final-validation evidence.
- Durably enqueue the matching merge before setting awaiting_merge or emitting ready.
- Preserve the commit-first ordering across crashes/restarts.
- Keep changes limited to the production path and directly necessary persistence/schema updates.

Acceptance:
- No awaiting_merge/ready transition can occur without a durable matching merge queue entry.
- Persisted evidence identifies the exact task, deliverable commit, and feature-base commit.
- Existing delivery behavior outside this boundary remains unchanged.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
