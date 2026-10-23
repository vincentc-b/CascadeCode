---
id: task_016_001_003
title: Add focused integration coverage for synchronization and lifecycle failures
tier: task
status: completed
parent: feat_016_001
children: []
depends_on:
- task_016_001_002
owners:
- swe
skills: []
parent_rev: 4a74bd1cf9be4a834804aa0f83cd7a10354e4857
created: '2026-10-23'
updated: '2026-10-23'
---
# Add focused integration coverage for synchronization and lifecycle failures

## Parent Feature

[feat_016_001](../../features/2_active/feat_016_001.md)

## Depends on

- task_016_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Prove the feature contract with focused, high-signal integration tests.

## Coverage

- Clean updates and already-current retries for epic, feature, and task integration worktrees.
- Persisted stacked feature predecessor remains the base after room settings change.
- Staged changes yield dirty_index; tracked unstaged and untracked changes yield local_changes; inputs remain untouched.
- Genuine conflicts report exact validated paths, remove MERGE_HEAD, and leave the original work-branch commit checked out.
- Concurrent update/lifecycle attempts serialize and in-flight items return busy.
- Task, feature, and epic lifecycle merge failures preserve state and return structured reasons.
- The activation-created epic pointer conflict remains the only automatically resolved conflict.

Avoid redundant unit cases where these behaviors are already exercised end to end.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
