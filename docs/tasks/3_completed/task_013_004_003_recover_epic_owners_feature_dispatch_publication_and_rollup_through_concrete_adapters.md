---
id: task_013_004_003
title: Recover Epic owners, Feature dispatch, publication, and rollup through concrete adapters
tier: task
status: completed
parent: feat_013_004
children: []
depends_on:
- task_013_004_001
owners:
- swe
skills: []
parent_rev: 2b8e5f1452993d96fc263be155cc99b87c2d0035
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Recover Epic owners, Feature dispatch, publication, and rollup through concrete adapters

## Parent Feature

[feat_013_004](../../features/2_active/feat_013_004.md)

## Depends on

- task_013_004_001

## Acceptance criteria

1. For a proven Epic symptom, verify the concrete Epic owner, registered worktree, exact action/review identity, current generation, and all plan/approval/comment/dependency gates. Preserve live owner, pending input/review, dirty worktree, cancellation/return and human decisions.
2. Execute legal Epic-team wakeup and direct-Feature dispatch/restoration through existing graph and supervision paths. Preserve Feature and Epic identities and original action provenance.
3. Retry owned branch/review publication, stacked-review gaps and completion closeout through existing durable paths. Reconcile terminal result once; a queued event or acknowledgement alone is pending.
4. Keep unknown mergeability, missing worktree and fetch/admission/validation/publication errors owned and retryable or actionable. Retain completed source through review/cleanup/rollup and preserve sibling blockers.

## Files likely touched

`cascade/epic/`, `cascade/workspace/kickoff.py`, `cascade/team_supervision.py`, `cascade/stacked_review_recovery.py`, `cascade/team_review_recovery.py`, `cascade/team_branch_recovery.py`, `cascade/watchdog/`; focused Epic/review tests.

## Implementation notes

Reuse Epic `supervise_child`, `retry_integration_branch_update`, `publish_review_resolution`, `reconcile_stacked_review_gap`, review health and existing completion reconciliation. Bind callable/result path to the exact Epic owner; recheck generation and gates before effects and after acknowledgement. Work in the registered product worktree and read board gates from the tracking root.

## Skills

_(none)_

## Test plan

Use an isolated repository and actual registered adapter to show a stalled Epic owner or unpublished local integration reaches review publication and closeout exactly once. Include plan approval and comment gates, pending review, split roots, restart and concurrent manual recovery. Reuse Epic 042 tests where practical.

## Out of scope

Feature-owned Task dispatch and UI/default-on controls.
