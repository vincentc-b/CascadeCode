---
id: task_018_001_002
title: 'Launcher: cascade up owns lock and listener, spawns worker in own process group, sweeps group and stale git locks, relaunches'
tier: task
status: completed
parent: feat_018_001
children: []
depends_on:
- task_018_001_001
owners:
- swe
skills: []
parent_rev: 8e301c52eed45258550b99738a6e2b7a3e2ced69
created: '2026-10-23'
updated: '2026-10-23'
---
# Launcher: cascade up owns lock and listener, spawns worker in own process group, sweeps group and stale git locks, relaunches

## Parent Feature

[feat_018_001](../../features/2_active/feat_018_001.md)

## Depends on

- task_018_001_001

## Scope change

After two stalled provider turns, the stale git lock sweep moved to task_018_001_004. This task kills the worker's process group but does not sweep git locks; the title still mentions the sweep only because the title is fixed.

## Acceptance criteria

- `cascade up` runs `prepare_up`, acquires `.cascade/supervisor.lock`, and binds the War Room listening socket exactly once.
- The worker runs in its own process group and receives the socket fd, readiness pipe fd and lock token per task_018_001_001's handshake.
- After any worker exit the launcher kills the worker's process group, calls a single post-exit hook (a no-op stub here; task_018_001_004 fills it with the git lock sweep), then applies the exit-code policy.
- Launcher PID and lock holder stay constant across worker restarts, and the listener is never closed.

## Files likely touched

The `cascade up` CLI entry and a new stdlib-only launcher module. Build on task_018_001_001's edit to `cascade/war_room/server.py`; do not duplicate it.

## Implementation notes

Rewrite `cascade up` as a small long-lived launcher. Its loop is stdlib-only and imports no changing Cascade modules after start.

- Bind the listening socket with a backlog so clients queue during restart gaps.
- Spawn `python -m cascade.workspace.worker` with `start_new_session=True`. Wait for readiness.
- Exit code handling: 0 = stop (launcher exits 0); 75 = update restart (respawn immediately on same socket); other = crash (respawn after a fixed 1s delay; bounded backoff belongs to the failure-containment feature).
- SIGINT/SIGTERM to the launcher: forward an operator stop to the worker, wait, kill the group, run the post-exit hook, exit 0 without relaunching.

Keep the change small. If a turn runs long, commit the working loop first.

## Skills

_(none)_

## Test plan

No separate unit tests; covered by task_018_001_003.

## Out of scope

Stale git lock sweep (moved to task_018_001_004). Bounded crash backoff.
