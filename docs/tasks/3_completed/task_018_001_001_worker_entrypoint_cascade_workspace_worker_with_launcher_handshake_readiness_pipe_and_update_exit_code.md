---
id: task_018_001_001
title: 'Worker entrypoint: cascade.workspace.worker with launcher handshake, readiness pipe, and update exit code'
tier: task
status: completed
parent: feat_018_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e7d5faa9c1ae1d0ecd540ead86d139fe182eae89
created: '2026-10-23'
updated: '2026-10-23'
---
# Worker entrypoint: cascade.workspace.worker with launcher handshake, readiness pipe, and update exit code

## Parent Feature

[feat_018_001](../../features/2_active/feat_018_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add `python -m cascade.workspace.worker` that serves the War Room on an inherited listening socket fd instead of binding its own.

- Refuse to start unless the launcher handshake is present: inherited socket fd + readiness pipe fd + lock token in env (names defined here and consumed by the launcher task). Exit non-zero with a clear message otherwise.
- Write a readiness message to the inherited pipe after the server is constructed and resume is scheduled.
- On detected Cascade source change (`cascade/**/*.py`), exit with code 75 (update). Operator stop (SIGTERM from launcher) exits 0. Any other failure is a crash (non-zero, not 75).
- Worker must not acquire `.cascade/supervisor.lock` itself; the launcher holds it.

Done when: worker runs only under the handshake, signals readiness, and uses exit codes 0/75/other as specified. No unit-test matrix; covered by the integration test task.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
