---
id: task_016_001_001
title: Implement branch synchronization domain service
tier: task
status: completed
parent: feat_016_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4a74bd1cf9be4a834804aa0f83cd7a10354e4857
created: '2026-10-23'
updated: '2026-10-23'
---
# Implement branch synchronization domain service

## Parent Feature

[feat_016_001](../../features/2_active/feat_016_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement the shared domain service for inspecting and updating active epic, feature, and task integration branches.

## Scope

- Resolve the canonical integration checkout without touching the operator checkout.
- Select the tier-aware base: product trunk for epics, persisted dispatch/review base for features, and parent feature branch for tasks.
- Compute local-ref ahead/behind counts.
- Define structured outcomes for dirty_index, local_changes, branch_conflict, busy, and invariant failures without exposing raw command output.
- Under the shared lifecycle process lock, require an active idle item on its expected branch and a fully clean worktree, including untracked files.
- Perform a normal base-into-work merge; make already-current retries successful no-ops.
- On conflict, return validated repository-relative unmerged paths, abort and verify cleanup, and restore the pre-update branch commit.

## Acceptance

The service meets the feature's inspection, preflight, serialization, no-op, and cleanup contracts for all three tiers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
