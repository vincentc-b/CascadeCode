---
id: task_026_002_003
title: Retry mechanically blocked queued merges
tier: task
status: completed
parent: feat_026_002
children: []
depends_on:
- task_026_002_001
- task_026_002_002
owners:
- swe
skills: []
parent_rev: b2d72c4bb274540f1fa2d709cbdf84ccfcc8407d
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Retry mechanically blocked queued merges

## Parent Feature

[feat_026_002](../../features/2_active/feat_026_002.md)

## Depends on

- task_026_002_001
- task_026_002_002

## Objective

Connect the existing durable pending-task-merge retry loop to the resumable-action state introduced by task 001, so a repaired mechanical precondition resumes the original merge action rather than relying only on the legacy queue entry.

## Scope

- Keep `cascade.task_rollup.retry_pending_task_merges` as the existing merge execution boundary; do not build a second merge queue.
- Create or load one stable persisted action for each queued task merge, using a deterministic identity derived from the task/merge being retried.
- When the mechanical prerequisite is repaired, retry that same persisted action and preserve its idempotency key across supervisor passes and restarts.
- Mark the action completed after a successful merge (including an already-completed equivalent), without invoking the merge or rollup twice.
- Persist a retryable/mechanical outcome for transient or repairable refusal.
- Expose an owner-decision/semantic-conflict outcome, with the existing conflict evidence, for task 004 to route. Do not resolve content or assign the owning tier in this task.
- Preserve the existing pending-merge file format unless a minimal compatibility change is required.
- Do not grant Task workers new Git or forge permissions.

## Acceptance criteria

- A queued merge blocked only by a repaired checkout/mechanical prerequisite automatically retries through the existing merge boundary.
- The retry uses the same durable action identity after process restart; it does not infer or mint a replacement action.
- Repeated supervisor passes after success are no-ops: no duplicate merge, rollup, or terminal-state regression occurs.
- A branch/content conflict is persisted as a semantic outcome with source/target/conflict evidence and is not automatically resolved.
- Existing callers of `queue_task_merge`, `pending_task_merges`, and `retry_pending_task_merges` remain compatible.
- No new Task-worker Git or forge capability is introduced.

## Files likely touched

- `cascade/task_rollup.py`
- `cascade/task/action_recovery.py` only if a small integration helper is needed
- Existing focused tests around pending task merges/action recovery

## Implementation notes

The repository already has an automatic pending-merge retry loop and tests. The required change is the narrow integration with the durable action state added on the feature branch, not another retry mechanism. Reuse existing merge-result reasons and conflict evidence. Leave owning-team selection and resolution resumption to task 004.

## Skills

_(none)_

## Test plan

Add or update focused integration-boundary scenarios proving:

1. repair then retry completes the original persisted merge action;
2. a second supervisor pass does not invoke merge/rollup again;
3. restart/load preserves the same action identity;
4. semantic conflict is persisted for later routing and remains unresolved.

Run the existing pending-task-merge and action-recovery regressions.

## Out of scope

- Automatic semantic conflict resolution.
- Feature-Team/Epic-Team ownership routing or resolution handling (task 004).
- A new queue, merge subsystem, or broad persistence redesign.
- Changes to Task worker permissions.
