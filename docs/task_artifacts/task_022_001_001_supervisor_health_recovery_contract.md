# task_022_001_001 — Supervisor health recovery contract

This discovery artifact records the implementation contract for
`feat_022_001`. It is separate from the board Task document because Task SWE
tools intentionally deny writes under `docs/tasks`.

## Hierarchy and authority

`WorkMeta.parent` and `children` describe epic -> feature -> task. Use the
merged board because documents may live in integration worktrees. Epics and
features are supervisors. Inspect only immediate children whose parent equals
the observer, and exclude supervisor-tier children. Automatic remediation
candidates are therefore owned tasks.

The Feature Team's `retry_task` wrapper validates that the target task belongs
to the invoking feature and dispatches as the authorized `boss` principal.
Observation must not bypass that boundary.

## Canonical states and transitions

Board frontmatter is lifecycle truth. Work statuses are `backlog`,
`ready_to_plan`, `active`, `blocked`, `completed`, `cancelling`, and
`cancelled`. Folder validity is part of state:

- `backlog` and `ready_to_plan`: `1_backlog`
- `active`, `blocked`, and `cancelling`: `2_active`
- `completed` and `cancelled`: `3_completed`

Exclude terminal completed/cancelled reports. Cancelling is ineligible while
terminalization is underway.

Relevant legal edges are backlog or ready-to-plan -> active through dispatch;
active -> blocked through task failure; blocked -> active only through task
dispatch; active -> completed through validated merge; and eligible nonterminal
-> cancelling -> cancelled through cancellation. A sweep must never write a
status directly.

Task execution records in `.cascade/executions.json` use phases `queued`,
`running`, `awaiting_merge`, `merge_blocked`, and `terminal`. Their
derived health is queued, healthy, stale, awaiting-merge, merge-blocked,
succeeded, or failed. Workspace supervisor states are `serving`, `draining`,
`restarting`, `update_blocked`, and `degraded`. These are operational
evidence, not new work statuses.

## Classification contract

- No action: terminal/supervisor exclusions; healthy or legitimately pending
  reports; active tasks awaiting merge or merge reconciliation.
- Remediation eligible: an owned task with canonical `blocked` status in
  `2_active`.
- Unresolved: folder/status inconsistencies, cancellation in progress,
  required-but-missing execution evidence, or refused/failed recovery.

Stale active tasks remain owned by the existing watchdog reclaim path and are
not a reason to call `retry_task`. Transient inspection/recovery failures must
not terminate the supervisor loop or be recorded as successful attempts.

## Safe recovery primitive

Recovery is exactly
`cascade.feature.recovery.retry_task(task_id, feature_id, root)`. It re-reads
the owned child, requires blocked state, and delegates to `dispatch_task`,
retaining dependency, cancellation, comment, parallelism, worktree, skill, and
boot gates. Success performs blocked -> active and `mark_queued` advances the
execution attempt.

`revise_task` mutates the plan and is not automatic remediation. Active-turn
restart/stall recovery and merge reconciliation retain their current ownership.

## Incident identity and concurrency

Stable child identity is `WorkMeta.id`. Each dispatch persists a monotonically
increasing execution `attempt`; within it, `phase` and `heartbeat_at`
version the observation. The board document also exposes its Git SHA.

Key a durable disposition by:

`(task_id, attempt, lifecycle_status, execution_phase, heartbeat_at)`

Use explicit nulls when no execution record exists. Claim/check the disposition
under the existing process lock and persist it beside execution state, following
the existing episode-keyed stall-disposition pattern. The same tuple permits at
most one action across repeated or concurrent sweeps. Successful retry changes
status and attempt. Do not key on date-granularity `updated`, an in-memory set,
or supervisor `updated_at`.

## Cadence

Use the existing watchdog maintenance cycle; add no thread, timer, or scheduler.
Later mutation work should follow the established `cascade.toml` reader
pattern: typed accessor, conservative default, positive numeric validation, and
documented invalid-value behavior. Invoke from the existing maintenance boundary
so draining/restart handling and loop exception containment remain intact.

## Tradeoffs

Persisting dispositions in the execution sidecar avoids polluting lifecycle
frontmatter and matches existing stall-recovery durability. Missing or corrupt
evidence must be unresolved rather than guessed safe.

Restricting automatic recovery to blocked leaf tasks is deliberately narrow, but
it is the only current parent-role-authorized primitive that re-enters every
normal dispatch gate. Existing stale-turn and merge paths remain independent.

## Follow-on acceptance coverage

Integration tests should cover healthy no-op, one eligible attempt, successful
blocked -> active recovery, terminal and supervisor exclusion, repeat/concurrent
sweep idempotency, and transient failure containment.
