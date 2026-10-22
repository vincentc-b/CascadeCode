---
id: task_017
title: Wire forced refresh and prove remote-backed workflow end to end
tier: task
status: completed
parent: feat_006
children: []
depends_on:
- task_015
- task_016
owners:
- swe
skills: []
parent_rev: 943c6f1f0eedd36540fc30c592e51e8131607be9
created: '2026-10-21'
updated: '2026-10-22'
---
# Wire forced refresh and prove remote-backed workflow end to end

## Parent Feature

[feat_006](../../features/2_active/feat_006.md)

## Depends on

- task_015
- task_016

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Complete the operator-facing synchronization path and prove the feature contract with one high-signal integration scenario.

## Scope
- Route the War Room polling endpoint/button and watchdog cadence through remote-backed synchronization.
- Return concrete forced-refresh errors while retaining the last valid snapshot and usable dispatch behavior.
- Update product/design documentation that promises a product-trunk fast-forward.
- Add an integration test starting from a local trunk with Cascade-only commits, merging a new brief to remote trunk, refreshing within the configured cadence, observing it in GET /api/board, and activating it.
- Assert checkout HEAD, branch, tracked edits, and active integration worktrees remain unchanged; repeat refresh to prove no duplicate rows or toasts.

## Verification
Run the focused refresh/board/activation/War Room suites plus existing active/completed precedence and feature/task dispatch tests. Prefer the integration scenario over redundant mock-only tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
