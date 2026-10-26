# Draft brief: Parent team recovery for interrupted tasks

## Intent

Let a Feature Team recover its active child Task when the worker stops before delivery. The parent should be able to request one safe restart using the existing Task branch, worktree, checkpoint, pinned Feature plan, provider settings, and skills. Cascade should decide whether to resume the worker or finish an already validated merge. Recovery must not require a human to edit execution state or run Git commands.

The failure in `task_022_002_002` illustrates the gap: `swe_run_tests` passed and marked the execution `awaiting_merge`, then a supervisor drain cancelled the turn before the changed files were committed. There was no pending merge, and restart recovery skipped the task because of its phase. The Feature Team's current `retry_task` control applies to failed Tasks, so it could not recover this active Task.

## Required behavior

1. Treat passing tests as validation evidence, not proof that the Task is ready to merge. Set `awaiting_merge` and show the ready toast only after a deliverable commit exists and a durable merge request has been queued. Preserve the latest test result across a drain so a resumed turn can reuse it only when the tested tree still matches the worktree.
2. Detect an active Task with no live owner that has neither a queued merge nor a completed merge. Surface `recovery_needed` with the reason and last progress time to its Feature Team and in the War Room. Include the missing-commit case even if an older execution record says `awaiting_merge`.
3. Add a Feature Team tool, `recover_task(task_id)`, limited to that team's direct child Tasks. The tool returns one of: merge queued, restart requested, already running, already complete, or a concrete blocker. The parent can invoke it without a separate human approval.
4. Under a durable per-Task lock, recheck the Task status, parent, owner lease, branch, worktree, checkpoint, test result, commit, and merge queue before acting. Repeated requests must create at most one new turn. Never replace a live owner based only on an old heartbeat; if the owner is stalled, use bounded cancellation and wait for lease release before restart.
5. If a validated deliverable commit exists, queue and retry the normal Task-to-Feature merge. If it does not, resume the SWE turn on `task/<id>` in its existing worktree. Preserve uncommitted files and use the saved checkpoint when valid; otherwise start a fresh turn with the Task plan, pinned Feature plan, changed-file summary, prior test result, provider/model settings, and skills. Do not reset, clean, or silently create a different branch.
6. After the resumed turn, run the normal scoped test and commit gates, then queue the merge. Report a failed restart, missing branch, unsafe worktree, test failure, or merge conflict as an actionable result to the parent. Keep ordinary merge conflicts on the existing merge-blocked path.

## Acceptance scenarios

- A drain after green `swe_run_tests` but before commit leaves a dirty Task worktree. Recovery resumes once, commits the tested change, and merges it into the Feature branch.
- A drain after commit but before merge queues the existing commit for merge without spawning a new SWE turn.
- Restart recovery finds the same orphan automatically; a simultaneous parent request does not create a second worker or duplicate merge.
- A live worker rejects a duplicate recovery request. A stalled worker is cancelled within a bound before a replacement takes ownership.
- A dirty worktree, missing branch, stale checkpoint, red tests, and a changed Feature head each preserve the Task's files and yield a clear recovery or blocker result.
- The parent cannot recover a Task owned by another Feature or change a completed or cancelled Task.
- The War Room does not show “ready to merge” until the commit and durable queue entry exist; it shows why an orphan needs recovery.

## Implementation boundaries

Use Cascade's existing execution lease, TaskRun/worktree registry, checkpoint, `swe_commit`, and pending merge queue. Store the recovery decision durably so a supervisor restart can replay it. Keep process cancellation and Git mutation inside the supervisor; the Feature Team receives a scoped recovery tool and result, not raw process or filesystem access. Recheck each precondition after acquiring the lock, and make the automatic orphan sweep and parent action call the same recovery function.

The first implementation should cover Feature Team recovery of child Tasks. Design the recovery result and ownership checks so the same pattern can later support Epic Team recovery of child Features.
