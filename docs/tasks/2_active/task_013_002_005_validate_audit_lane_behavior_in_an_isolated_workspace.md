---
id: task_013_002_005
title: Validate audit lane behavior in an isolated workspace
tier: task
status: active
parent: feat_013_002
children: []
depends_on:
- task_013_002_004
owners:
- swe
skills: []
parent_rev: fb2b460d2c7a5ee0584f265da6096d08bd8227fa
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate audit lane behavior in an isolated workspace

## Parent Feature

[feat_013_002](../../features/2_active/feat_013_002.md)

## Depends on

- task_013_002_004

## Acceptance criteria

1. In a real isolated workspace, a blocked ordinary startup maintenance or watchdog chain does not prevent the independent audit lane from progressing. Operator stop cancels the lane promptly, while source-update and crash shutdown retain their distinct worker outcomes.
2. A trunk process and processes launched from owned product or tracking worktrees contend for one canonical workspace claim and receipt, including split ProjectContext. Spawning the observer while a parent thread holds a board lock cannot inherit that lock and stall the pass.
3. One absolute monotonic deadline covers candidate discovery, process startup/import, document-revision and child/readiness Git reads, observation, coordination, and capability probing. Cancellation and timeout terminate or reap observer and Git descendants, including TERM-ignoring helpers and helpers left by an observer that already exited, before the workspace claim is released. A later pass can safely reacquire the claim.
4. At most 100 items and 60 seconds of observer/coordinator work occur per pass. Repeated slow first candidates, missing or unavailable candidate evidence, and a page that exceeds one pass budget retain precise unavailable evidence and advance fairly without claiming unobserved work healthy. Completed prefixes and opaque cursor continuation survive timeout and restart; later items and tiers are eventually reached.
5. Disabled periodic scheduling admits no periodic work. Explicit manual requests are guarded, coalesce with an in-flight pass, preserve the periodic deadline, and give a failed manual request bounded retry/cooldown or truthful actionable resubmission. Restart coalesces overdue periods into one pass; clock jumps and bounded nonnegative jitter cause no storm.
6. Proven recovery goes through the canonical incident classification, capability probe, fresh locked reservation, and existing supervised owner worker in the supervisor runtime. Demonstrate at least one real adapter operation after reservation; a spawned observer never starts an orphan model turn or second recovery engine. Missing capability and timeout evidence remain actionable.
7. Healthy passes write only the compact untracked receipt, without board watcher, dispatch, notification, Git write, or provider side effects. Failed or busy passes do not record completed receipts. Final validation is run on the clean committed integrated feature head after all product commits.

## Files likely touched

- tests/watchdog and tests/workspace integration coverage
- audit lane, observation, and worker code only to correct failures found by these checks
- project documentation for receipt behavior and legacy maintenance convergence

## Implementation notes

Use controllable clocks and real isolated workspace/process coordination. Preserve the imported Epic base, canonical claim and startup cleanup, shutdown-cause separation, and the temporary scaffold release gate. Production default-on activation remains gated to feat_013_005 after real all-tier repair acceptance. Keep recovery handoff in existing supervised workers outside observer children and broad locks. Record exact test commands/results and any accepted limits in the feature handoff.

## Skills

_(none)_

## Test plan

Run high-signal integration cases for every acceptance item, including real process contention, blocked document-revision Git, TERM-ignoring descendant cleanup, repeated slow/missing candidate continuation across passes and restart, disabled manual retry, adapter-through-reservation, and blocked maintenance plus operator stop. Commit the final product changes first; then run the relevant Cascade-supervised suite on the clean committed head and capture its final-validation evidence. Run focused static checks where applicable.

## Out of scope

Production default-on activation before feat_013_005 and a new recovery engine, queue, or model owner.
