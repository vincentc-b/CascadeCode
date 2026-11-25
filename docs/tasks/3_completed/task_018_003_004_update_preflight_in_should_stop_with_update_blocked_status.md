---
id: task_018_003_004
title: Update preflight in should_stop with update_blocked status
tier: task
status: completed
parent: feat_018_003
children: []
depends_on:
- task_018_003_001
- task_018_003_002
owners:
- swe
skills: []
parent_rev: a650ec93757565beabb62a80700efd2d29539047
created: '2026-10-23'
updated: '2026-10-23'
---
# Update preflight in should_stop with update_blocked status

## Parent Feature

[feat_018_003](../../features/2_active/feat_018_003.md)

## Depends on

- task_018_003_001
- task_018_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

- In the source-change branch of `run_worker`'s `should_stop`, **before** `begin_drain()`, run a short-lived subprocess on the new source that imports the Cascade entry modules and runs `prepare_up` (validate only; it takes no lock). Hard timeout of about 30s; a timeout counts as failure.
- On failure: keep serving, do not drain, and write `update_blocked` with the error output via the shared status helper. Remember the failed fingerprint so it retries only on the next change. On success: proceed to `begin_drain()` as today.
- Operator stop and launcher-loss skip the preflight. Keep the launcher-loss check as the first line of `should_stop`.

Integration test (a): introducing a syntax error into the source triggers `update_blocked`, and the old worker keeps answering requests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
