---
id: task_018_003_001
title: 'Status foundation: stdlib fingerprint, sweep return data, launcher state transitions and supervisor_status.json'
tier: task
status: completed
parent: feat_018_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 0ef9594c73b82301bd44659f791beb888de70e7e
created: '2026-10-23'
updated: '2026-10-23'
---
# Status foundation: stdlib fingerprint, sweep return data, launcher state transitions and supervisor_status.json

## Parent Feature

[feat_018_003](../../features/2_active/feat_018_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Seams only; no behavior change beyond logging and the status file.

- Move `_source_fingerprint` from `cascade/workspace/up.py` into a stdlib-only module; `up.py` re-exports it. The launcher imports it once at start.
- `sweep_stale_git_locks` (git_lock_sweep.py) returns removed lock paths plus any product-trunk `.git/index.lock` path instead of `None`; `post_worker_exit` passes it on.
- Stdlib-only status helper: atomic write (tmp + os.replace) of `.cascade/supervisor_status.json` with fields `state` (serving|draining|restarting|update_blocked|degraded), `worker_pid`, `restart_count`, `last_error` {exit_code, stderr_tail, message}, `next_action`, `trunk_lock_warning`, `since`, `updated_at`. Also a reader. The worker uses the same helper later (dec_016).
- Add one launcher transition function that every state change goes through: it logs one stderr line and writes the status file. Replace the ad hoc `print` calls in `launcher.py`.

Tests: none of its own. Covered by the feature's integration tests (spec: seam changes ride on them).

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
