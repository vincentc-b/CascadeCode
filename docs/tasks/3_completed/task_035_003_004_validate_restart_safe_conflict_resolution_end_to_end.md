---
id: task_035_003_004
title: Validate restart-safe conflict resolution end to end
tier: task
status: completed
parent: feat_035_003
children: []
depends_on:
- task_035_003_003
owners:
- swe
skills: []
parent_rev: 8c67c7bdb472700157994514ce73ca52c5e00666
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Validate restart-safe conflict resolution end to end

## Parent Feature

[feat_035_003](../../features/2_active/feat_035_003.md)

## Depends on

- task_035_003_003

## Acceptance criteria

- A PR #147-style `action_recovery.py` semantic conflict is persisted and reported as a durable, resumable blocker with recovery evidence.
- A PR #148-style clean rebase completes successfully through the normalized provider contract.
- Representative checkpoint interruptions do not duplicate commits, pushes, reviews, War Room messages, or lifecycle events.
- A remote-head race yields a safe retry/reconciliation or a correctly evidenced blocker.
- Focused acceptance commands and expected results are captured in the test implementation or task handoff without modifying board-owned markdown from the task branch.

## Files likely touched

- `cascade/review_rebase.py` only if a minimal acceptance-enabling correction is required.
- `tests/test_review_rebase.py` for focused integration/acceptance coverage.
- Other runtime or test files only when directly required by the acceptance scenarios.
- Do not modify `docs/**`, `.cascade/**`, or other board-owned planning artifacts from the task branch.

## Implementation notes

## Scope

Add high-signal integration/acceptance coverage for the complete restart-safe workflow across the normalized provider contract.

Preserve the existing worktree changes that satisfy this scope, but remove/revert the out-of-scope task-document change before committing. The prior attempt failed the commit guard because it touched a forbidden board-owned path; this is not authorization to bypass that guard.

## Required outcomes

- Reproduce and validate the PR #147-style `action_recovery.py` semantic conflict as a durable, resumable blocker.
- Validate the PR #148-style clean rebase through successful completion.
- Exercise interruption at representative checkpoints and confirm no duplicate commits, pushes, reviews, messages, or lifecycle events.
- Exercise a remote-head race and confirm safe retry/reconciliation or a correctly evidenced blocker.
- Report the minimal commands and expected results needed to verify acceptance in the task result.

## Skills

_(none)_

## Test plan

Run the focused `tests/test_review_rebase.py` cases covering semantic conflict, clean completion, interruption/idempotency, remote-head movement, and normalized provider outcomes. Broaden only if focused results expose a regression boundary.

## Out of scope

- Changes to board-owned markdown or task/feature specs from the implementation branch.
- Broad unrelated rebase or provider refactors.
- Redundant test expansion beyond the feature’s named acceptance scenarios.
