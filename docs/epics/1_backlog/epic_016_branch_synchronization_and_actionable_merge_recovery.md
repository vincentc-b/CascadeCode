---
id: epic_016
title: Branch synchronization and actionable merge recovery
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Branch synchronization and actionable merge recovery

## Intent

Make integration drift and merge failures recoverable from the War Room. Operators should be able to update an epic, feature, or task branch from its actual parent/base without leaving the board, and close or merge failures must distinguish local checkout changes from genuine branch conflicts and identify the blocking paths.

### Success criteria

- Active epic, feature, and task cards expose an Update branch action when their integration branch is behind its resolved parent/base.
- Updating uses a normal merge in the work item's integration worktree and never rebases or force-pushes published branches.
- The target is tier-aware: product trunk for epics, the configured review base for features (including stacked predecessors), and the parent feature for tasks.
- Update is allowed only while the work item is idle and its integration worktree is clean; retries are idempotent and serialized with lifecycle operations.
- A failed update aborts cleanly and reports the exact conflicting paths without leaving MERGE_HEAD or an ambiguous worktree state.
- Epic close and task/feature integration distinguish dirty_index, local_changes, and branch_conflict rather than collapsing failed Git commands into merge_conflict.
- The War Room shows ahead/behind state and actionable recovery text, then allows the original close or merge action to be retried.
- Tests cover clean updates, stacked-feature base selection, dirty worktrees, true conflicts, concurrent lifecycle attempts, and the activation-created epic pointer conflict.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Preserve the operator checkout and all user changes. Do not automatically stash, discard, reset, rebase, force-push, or resolve semantic conflicts. Reuse integration worktrees and existing branch/review identity. Keep the activation-created trunk-pointer resolution narrowly allowlisted. Surface diagnostics without exposing arbitrary command output. The existing default-off stacked-PR behavior and durable PR target selection remain authoritative.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
