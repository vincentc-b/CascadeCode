---
id: epic_027
title: Recover orphaned Task deliveries
tier: epic
status: active
parent: null
children:
- feat_027_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-26'
updated: '2026-10-31'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Recover orphaned Task deliveries

## Intent

The Feature Team should detect and recover an active child Task whose worker has stopped before delivery finishes. A green test result must not make the Task appear ready to merge until a validated deliverable commit and durable merge queue entry exist. Recovery should finish the existing Task or resume its worker without a human editing Git or runtime state.

Task `task_026_002_004` exposed the gap: the ready toast preceded its commit, execution remained `awaiting_merge` with no live owner or pending merge, and the existing parent health sweep treated it as healthy. The earlier draft in `docs/briefs/parent_team_task_recovery.md` describes the same interrupted-delivery case.

### Success criteria

- The parent health sweep compares Task status and execution phase with owner lease, worktree, deliverable commit, validation evidence, and merge queue. An active Task with no live owner and no pending or completed merge is `recovery_needed`, including when its stored phase says `awaiting_merge`.
- Set `awaiting_merge` and emit the ready toast only after a matching validated commit and durable merge request are recorded. A passing test alone remains validation evidence, tied to the tree it tested.
- The supervisor performs one serialized, durable recovery decision per Task incident. If a valid deliverable commit exists, it requeues the same Task merge. Otherwise it resumes the existing Task branch, worktree, and checkpoint, preserving files and pinned provider, model, skills, Task plan, and Feature plan.
- The owning Feature Team can request `recover_task(task_id)` for a direct child and receives a precise outcome. The periodic sweep and this tool use the same recovery operation; a simultaneous request or supervisor restart cannot spawn two workers or merge twice.
- A live owner, unsafe worktree, changed test tree, missing branch, red tests, and semantic merge conflict yield explicit blockers. Unresolved recovery appears in the parent state and War Room; recovery clears only the derived blocker.

## Delivery contract

A Task becomes merge-ready only in this order:

1. `swe_commit` produces the deliverable commit on the existing Task branch.
2. Final validation runs against that exact commit and records the commit SHA and Feature-base SHA.
3. The durable pending merge request is recorded for the same Task, deliverable SHA, and base SHA.
4. Only then may execution enter `awaiting_merge` and emit the ready notification.

Pre-commit test runs remain useful feedback but never satisfy final delivery validation. If either the deliverable tree or Feature base changes, final validation must run again. This commit-first final validation contract removes the need to infer an exact tested tree from a drained dirty worktree.

## Macro-architecture

Extend the existing supervisor direct-report health sweep and Task lifecycle boundaries. Give the recovery operation a stable Task incident identity and acquire the Task lifecycle lock before rechecking board state, lease, worktree, checkpoint, commit, validation, and queue. Treat a commit with matching final validation as a merge-repair case; treat every other incomplete delivery as a resume case. Reuse the existing pending merge queue, SWE execution, and parent blockage provenance.

Make the commit-to-validation-to-queue transition restart-safe. On a later sweep, reconstruct the correct state from durable evidence instead of trusting the `awaiting_merge` label. Give the Feature Team a scoped recovery tool that requests supervisor action and reports its result; process cancellation and Git mutation remain in the supervisor.

## Cross-module constraints

- Preserve uncommitted work and the existing Task branch. Never reset, clean, stash, force-push, or silently create a replacement branch.
- Do not reuse final validation after the deliverable commit or Feature base changes.
- Do not replace a live owner based only on heartbeat age; cancel a stalled owner within a bound and wait for lease release before resuming.
- Keep retries bounded and idempotent across concurrent sweeps, parent requests, and supervisor restarts. Respect existing ownership, review, and merge-conflict gates.
- Reuse the current health sweep and action-recovery state; avoid a second scheduler or status store.
- Recovery may clear only the blocker provenance created for the same recovery incident.

## Core dependencies

- Task execution lease, checkpoint, worktree registry, `swe_run_tests`, and `swe_commit`.
- Durable pending Task merge queue and normal Task-to-Feature merge path.
- Feature Team tool boundary and supervisor direct-report health sweep.
- Existing parent blockage provenance and War Room status model.

## Feature breakdown
- feat_027_001

### 1. Enforce the durable Task delivery boundary

Make commit, exact-commit final validation, durable queue insertion, `awaiting_merge`, and ready notification follow the delivery contract. Persist enough evidence to compare Task ID, deliverable SHA, and Feature-base SHA after restart. Cover drains after commit and after validation, changed-tree/base revalidation, red validation, and replay without duplicate queue entries.

### 2. Detect and recover orphaned Task delivery

Extend the direct-report health sweep and shared supervisor recovery operation. Under the Task lifecycle lock, derive a stable incident, recheck live ownership and durable evidence, then either requeue a matching validated commit or resume the existing execution context. Preserve dirty worktrees and pinned execution inputs. Cover drain before commit, drain before queueing, restart replay, live-owner protection, unsafe/missing Git state, bounded cancellation, and concurrent recovery requests.

Depends on Feature 1.

### 3. Expose scoped recovery and recovery state

Add the owning Feature Team's `recover_task(task_id)` request using the same supervisor operation. Return precise outcomes (`not_needed`, `owner_live`, `requeued`, `resumed`, `in_progress`, or `blocked` with reason). Surface unresolved incidents through existing parent blockage provenance and War Room state, including semantic merge conflict, and clear only the matching derived blocker. Cover authorization to direct children, simultaneous tool/sweep requests, outcome rendering, and blocker lifecycle.

Depends on Feature 2.

## Explicit exclusions

- Recovery of non-Task descendants or Tasks owned by another Feature Team.
- A new scheduler, merge queue, status store, replacement branch, or generic Git repair tool.
- Automatic resolution of semantic merge conflicts, red tests, unsafe worktrees, or missing branches.
- Reworking unrelated notification, lease, or checkpoint behavior.

## Open questions

_(none)_

## Decision log

- 2026-10-26 · Human · Brief proposed after Task `task_026_002_004` required a manual merge requeue.

- `dec_001` · 2026-10-31 · Epic Manager · **Delivery contract**
  Chose Require commit-first final validation keyed by Task ID, deliverable commit SHA, and Feature-base SHA before durable merge queue insertion, awaiting_merge, or the ready notification..
  Rationale: A drained dirty worktree has no reliably durable identity. Validating the actual deliverable commit makes restart checks exact and forces revalidation whenever the deliverable or base changes.
  Honors: Success criteria requiring a matching validated commit and durable merge request; smallest restart-safe design without a new artifact system..

- `dec_002` · 2026-10-31 · Epic Manager · **Feature breakdown**
  Chose Sequence three features: durable delivery boundary; orphan detection and recovery; scoped parent control and recovery visibility..
  Rationale: The recovery engine depends on trustworthy durable evidence, while the parent tool and presentation should reuse the proven engine rather than create a parallel path.
  Honors: Ruthless prioritization, shared recovery semantics, and integration ownership with minimal cross-feature coupling..
## Amendment log

_(none)_
