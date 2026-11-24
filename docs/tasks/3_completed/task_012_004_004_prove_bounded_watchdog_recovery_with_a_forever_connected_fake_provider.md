---
id: task_012_004_004
title: Prove bounded watchdog recovery with a forever-connected fake provider
tier: task
status: completed
parent: feat_012_004
children: []
depends_on:
- task_012_004_003
owners:
- swe
skills: []
parent_rev: 2c0e7cf7161451eaf62e8ca911b1817a21e34e56
created: '2026-10-23'
updated: '2026-10-23'
---
# Prove bounded watchdog recovery with a forever-connected fake provider

## Parent Feature

[feat_012_004](../../features/2_active/feat_012_004.md)

## Depends on

- task_012_004_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add a high-signal integration/regression test for the complete feature contract.

Scenario:
- A fake provider call remains connected forever, emits no provider events or completed tool calls, and never advances checkpoint or task-worktree content.

The test must prove:
- Detection occurs within the configured bounded no-progress deadline using an injected monotonic clock.
- Only the affected turn's provider/bridge process tree is cancelled, including bounded escalation behavior where applicable.
- The supervisor, War Room, watchdog, and unrelated turns survive.
- The dirty task worktree and last checkpoint/result evidence remain intact.
- Exactly one actionable durable diagnostic is recorded with the required safe fields.
- At most one supervised recovery is scheduled for the unchanged episode despite repeated polling/callbacks.

Prefer this integration test over redundant mock-heavy unit coverage; add only the fixtures needed to make failures deterministic.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
