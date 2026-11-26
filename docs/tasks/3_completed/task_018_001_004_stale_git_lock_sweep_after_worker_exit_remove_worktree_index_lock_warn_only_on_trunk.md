---
id: task_018_001_004
title: 'Stale git lock sweep after worker exit: remove worktree index.lock, warn-only on trunk'
tier: task
status: completed
parent: feat_018_001
children: []
depends_on:
- task_018_001_002
owners:
- swe
skills: []
parent_rev: 1a86ddefaff8bbfaf28d9990949bf2400b018cb0
created: '2026-10-23'
updated: '2026-10-23'
---
# Stale git lock sweep after worker exit: remove worktree index.lock, warn-only on trunk

## Parent Feature

[feat_018_001](../../features/2_active/feat_018_001.md)

## Depends on

- task_018_001_002

## Acceptance criteria

- A stdlib-only function `sweep_stale_git_locks(repo_root)` removes `.git/index.lock` (and the worktree's gitdir `index.lock`) for every worktree under `.cascade/worktrees/*`, logging one line per removal.
- A leftover `index.lock` in the product trunk is never removed; the function logs one warning line instead.
- The launcher calls it after every worker exit, after the worker's process group has been killed, and on the SIGINT/SIGTERM shutdown path (epic dec_007).

## Files likely touched

The launcher module from task_018_001_002, or a sibling stdlib-only module.

## Implementation notes

Split out of task_018_001_002 after two stalled provider turns (feature dec_001).

Keep it in the launcher module or a sibling stdlib-only module so the launcher still imports no changing Cascade modules after start. Wire it into the post-exit hook left by task_018_001_002.

## Skills

_(none)_

## Test plan

No separate unit tests; covered by the integration test in task_018_001_003 (planted worktree `index.lock` is removed).

## Out of scope

Other lock types (`HEAD.lock`, ref locks); bounded backoff.
