---
id: epic_016
title: Branch synchronization and actionable merge recovery
tier: epic
status: active
parent: null
children:
- feat_016_001
- feat_016_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-23'
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

Introduce one domain-level branch synchronization and merge-diagnostics boundary beside the existing integration-worktree primitives. It resolves a work item's durable integration checkout and tier-aware base, computes ahead/behind state from local refs, and performs a normal base-into-work merge. Feature base resolution must reuse the persisted dispatch/review target selected by the existing stacked-PR flow; it must not infer a new target from current room settings.

All branch-changing operations run under the lifecycle process lock. Before merging, the service verifies that the item is active and idle, the expected integration checkout owns the expected branch, and the checkout has neither staged, tracked unstaged, nor untracked changes. A successful retry with no commits to integrate is a no-op success. On Git failure, the service captures only structured status and unmerged paths, aborts the merge, verifies that merge state is gone, and returns a typed result rather than raw command output.

Refactor the existing task, feature, and epic merge paths to use the same preflight and diagnostic vocabulary. Preserve the narrowly allowlisted epic activation-pointer resolution in epic promotion; every other unmerged path is a branch_conflict. Keep lifecycle state transitions after a successful merge only.

Extend the board read model with per-active-item synchronization state: resolved base branch, ahead count, behind count, eligibility, and a stable disabled reason. Add one War Room update endpoint that delegates to the domain service and returns its typed result. Active cards render Update branch only when behind, disable it with the server-provided reason when unsafe, and translate typed failures into recovery guidance that names conflicting paths. A successful update refreshes the board; failed close/merge actions retain the item and invite update/retry.

## Cross-module constraints

Preserve the operator checkout and all user changes. Do not automatically stash, discard, reset, rebase, force-push, or resolve semantic conflicts. Reuse integration worktrees and existing branch/review identity. Keep the activation-created trunk-pointer resolution narrowly allowlisted. Surface diagnostics without exposing arbitrary command output. The existing default-off stacked-PR behavior and durable PR target selection remain authoritative.

Do not fetch or mutate remotes as part of Update branch; compare and merge the locally resolved base ref. Treat untracked files as local_changes for update and lifecycle merge safety. Return repository-relative, validated conflict paths only. Do not retire worktrees, move board documents, or emit completion events on any failed merge.

## Core dependencies

- `cascade.workspace.integration_worktree` for canonical branch/worktree identity and trunk discovery.
- `cascade.workspace.trunk.resolve_product_trunk` for epic bases.
- Persisted feature dispatch/review selection in `cascade.stacked_dispatch` for feature bases.
- Existing board parent metadata for task bases.
- `cascade.board.lock.process_lock` for serialization with dispatch, rollup, completion, and board writes.
- `cascade.boss.merge` and `cascade.boss.epic_complete` for lifecycle merge integration and the activation-pointer exception.
- War Room board serialization, POST routing, and active-card rendering for state and actions.

## Feature breakdown
- feat_016_002
- feat_016_001

1. **Branch synchronization service and structured lifecycle merge failures**
   - Resolve tier-aware bases from authoritative persisted state.
   - Compute ahead/behind state and enforce active, idle, canonical, clean-worktree preconditions.
   - Merge the resolved base into the integration branch under the shared lifecycle lock, with idempotent no-op retries.
   - Abort failed merges, verify cleanup, and return typed dirty_index, local_changes, and branch_conflict results with validated paths.
   - Reuse the result contract in task/feature integration and epic promotion while preserving the activation-pointer exception.
   - Cover clean/no-op updates, each tier's base selection including a stacked feature, dirty states, conflict cleanup, lifecycle serialization, and pointer promotion.

2. **War Room update action and actionable recovery**
   - Serialize per-card ahead/behind and update eligibility for active epics, features, and tasks.
   - Add the update endpoint and active-card control using the service contract.
   - Present specific recovery text for dirty index, local changes, branch conflicts, busy work, and failed close/merge attempts; include conflict paths without raw Git output.
   - Refresh board state after success and preserve a straightforward retry path for update, task merge, and epic close.
   - Add focused route/serialization tests and browser-level interaction coverage for visibility, disabled states, success refresh, and failure guidance.

Feature 2 depends on Feature 1.

## Open questions

- None. Planning defaults to local refs only, strict clean-worktree safety including untracked files, and persisted feature base identity.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-23 · Epic Manager · **Macro-architecture**
  Chose Use one shared branch synchronization and typed merge-diagnostics boundary for manual updates and lifecycle merges..
  Rationale: Task, feature, and epic merge paths currently share Git mechanics but collapse distinct failure modes. A single boundary prevents policy drift, centralizes cleanup guarantees, and gives the War Room one stable contract.
  Honors: Success criteria for safe updates, actionable merge recovery, idempotency, and lifecycle serialization..

- `dec_002` · 2026-10-23 · Epic Manager · **Cross-module constraints**
  Chose Resolve feature update bases from the persisted dispatch/review selection, not the current stacked-PR toggle or a newly inferred dependency target..
  Rationale: A published feature branch must continue to track the durable base chosen when its review identity was established; recomputing from mutable room settings could silently change merge topology.
  Honors: The existing default-off stacked-PR behavior and durable PR target selection remain authoritative..

- `dec_003` · 2026-10-23 · Epic Manager · **Feature breakdown**
  Chose Deliver the epic as two ordered features: the synchronization/diagnostics domain service first, then War Room state and controls..
  Rationale: The UI depends on a stable typed backend contract, while lifecycle correctness can be implemented and tested independently. Two slices are the smallest split that preserves clear ownership without fragmenting Git policy.
  Honors: Ruthless scope control and focused, high-signal integration testing..
## Amendment log

_(none)_
