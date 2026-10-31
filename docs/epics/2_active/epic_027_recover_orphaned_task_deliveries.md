---
id: epic_027
title: Recover orphaned Task deliveries
tier: epic
status: active
parent: null
children: []
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

## Macro-architecture

Extend the existing supervisor direct-report health sweep and Task lifecycle boundaries. Give the recovery operation a stable Task incident identity and acquire the Task lifecycle lock before rechecking board state, lease, worktree, checkpoint, commit, tests, and queue. Treat a valid commit as a merge-repair case; treat an incomplete delivery as a resume case. Reuse the existing pending merge queue, SWE execution, and parent blockage provenance.

Make the test-to-commit-to-queue transition restart-safe. On a later sweep, reconstruct the correct state from durable evidence instead of trusting the `awaiting_merge` label. Give the Feature Team a scoped recovery tool that requests supervisor action and reports its result; process cancellation and Git mutation remain in the supervisor.

## Cross-module constraints

- Preserve uncommitted work and the existing Task branch. Never reset, clean, stash, force-push, or silently create a replacement branch.
- Do not reuse a green test result after the tested tree or Feature base changes without revalidation.
- Do not replace a live owner based only on heartbeat age; cancel a stalled owner within a bound and wait for lease release before resuming.
- Keep retries bounded and idempotent across concurrent sweeps, parent requests, and supervisor restarts. Respect existing ownership, review, and merge-conflict gates.
- Reuse the current health sweep and action-recovery state; avoid a second scheduler or status store.

## Core dependencies

- Task execution lease, checkpoint, worktree registry, `swe_run_tests`, and `swe_commit`.
- Durable pending Task merge queue and normal Task-to-Feature merge path.
- Feature Team tool boundary and supervisor direct-report health sweep.
- Existing parent blockage provenance and War Room status model.

## Feature breakdown

The Epic Team will sequence the durable delivery invariant, automatic orphan detection and recovery, and parent/War Room feedback. Integration coverage must include a drain after green tests but before commit, a drain after commit but before queueing, simultaneous parent and sweep requests, restart replay, live-owner protection, changed-tree revalidation, and a semantic merge blocker.

## Open questions

- Which existing validation artifact can reliably identify the exact tested tree across a drain?

## Decision log

- 2026-10-26 · Human · Brief proposed after Task `task_026_002_004` required a manual merge requeue.

## Amendment log

_(none)_
