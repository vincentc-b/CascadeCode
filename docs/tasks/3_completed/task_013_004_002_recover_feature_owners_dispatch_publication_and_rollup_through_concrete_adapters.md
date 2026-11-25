---
id: task_013_004_002
title: Recover Feature owners, dispatch, publication, and rollup through concrete adapters
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
# Recover Feature owners, dispatch, publication, and rollup through concrete adapters

## Parent Feature

[feat_013_004](../../features/2_active/feat_013_004.md)

## Depends on

- task_013_004_001

## Acceptance criteria

1. For a proven Feature symptom, verify the concrete Feature owner, registered product worktree, exact action/review identity, current generation, and legal board gates before effect. A live owner, pending input/review, dirty worktree, cancellation/return, or human gate is protected.
2. Execute Feature-team owner wakeup and authorized direct-Task dispatch/restoration through existing graph and supervision paths; preserve Task and Feature identities and original action IDs.
3. Retry owned integration-branch or review publication through existing durable actions; reconcile completed local work, review state and Feature rollup idempotently. A sent event or acknowledgement without a result remains pending.
4. Preserve split tracking/product roots, approval/sign-off/comment/dependency checks and concurrent manual recovery. Failures retain an owned retryable or actionable receipt and the completed source until terminal reconciliation.

## Files likely touched

`cascade/feature/`, `cascade/workspace/kickoff.py`, `cascade/team_supervision.py`, `cascade/team_review_recovery.py`, `cascade/team_branch_recovery.py`, `cascade/watchdog/`; focused Feature/review tests.

## Implementation notes

Reuse `supervise_child`, `recover_task`, `retry_integration_branch_update`, `publish_review_resolution`, review health and existing completion reconciliation. Bind callable and durable result path for the concrete Feature owner; keep the broad audit lock out of Git/model/forge work. Recheck generation and gates at the adapter boundary and after acknowledgement. Do not create a second queue or bypass owner authorization.

## Skills

_(none)_

## Test plan

Use an isolated repository and actual registered adapter to show absent/completed Feature owner or stranded local integration reaches owned review publication and rollup exactly once. Include pending input/review, live slow owner, split roots, dirty worktree and manual-recovery race. Reuse existing Feature and Epic 042 fixtures where practical.

## Out of scope

Epic owner/Feature dispatch and UI/default-on controls.
