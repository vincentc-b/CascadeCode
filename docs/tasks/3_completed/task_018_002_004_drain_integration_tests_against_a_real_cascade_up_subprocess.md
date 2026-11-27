---
id: task_018_002_004
title: Drain integration tests against a real cascade up subprocess
tier: task
status: completed
parent: feat_018_002
children: []
depends_on:
- task_018_002_001
- task_018_002_002
- task_018_002_003
owners:
- swe
skills: []
parent_rev: 981405a52ac07b3bf0bbb0ff11a99e21b19606a9
created: '2026-10-23'
updated: '2026-10-23'
---
# Drain integration tests against a real cascade up subprocess

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

- task_018_002_001
- task_018_002_002
- task_018_002_003
- task_018_002_005 (HTTP drain conformance; not in the board dependency list because the board cannot add dependencies to a minted task; see feature dec_014). Do not start until 005 has merged into `feat/feat_018_002`.

## Acceptance criteria

- (a) A write in flight when the update triggers is persisted and acknowledged; a write arriving during drain gets `503` with body `{"error":"updating"}` and `Connection: close`, while a GET during drain still succeeds.
- (b) Replay contract: a fake-provider turn calls `record_decision` and `mint_feature`, outlives the drain window, is cancelled, and is resumed once after restart; the board shows exactly one decision and one feature, and the task is not marked failed. This covers the replay-safe tools and atomic writes from task_018_002_001 and the `TurnCancelledForDrain` path from task_018_002_003.
- (c) An event queued during drain is delivered after restart.
- No per-tool idempotency unit-test matrix, no atomic-write unit test, no turn-registry unit tests.
- Deterministic: poll board state and HTTP responses; no sleeps longer than the configured drain window.

## Files likely touched

New test module(s) under `tests/` next to feat_018_001's relaunch test; shared fixtures from `tests/harness` / `tests/workspace`.

## Implementation notes

Before writing tests, confirm on `feat/feat_018_002` that `cascade/workspace/drain.py` exists, `worker_draining_event()` and `join_http_handlers` are gone, and `drain_and_shutdown` calls `server.shutdown()` only after the snapshot join and turn drain. If any is missing, raise it upward instead of fixing it here; test (a)'s 503 assertion will fail against an early `server.shutdown()`.

See the feature spec's "Test seams" section. Set `[worker] drain_seconds` small (for example 2) in the fixture `cascade.toml`. Trigger the update by touching a file under `cascade/` in the subprocess's source tree, as feat_018_001's relaunch test does. The fake provider runs through `run_role`, so it registers with `pid=None` and is cancelled by `task.cancel`. Reuse the existing harness rather than building a new one.

If (b) fails because a role node checkpoints on exception, raise it upward rather than adding per-tool checkpoints.

## Skills

_(none)_

## Test plan

The three tests above are the test plan; run them plus the existing suite.

## Out of scope

Tests for zero-downtime overlap, launcher behavior beyond what feat_018_001 already tests, and per-tool unit tests.
