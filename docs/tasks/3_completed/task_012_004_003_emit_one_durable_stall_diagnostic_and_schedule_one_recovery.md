---
id: task_012_004_003
title: Emit one durable stall diagnostic and schedule one recovery
tier: task
status: completed
parent: feat_012_004
children: []
depends_on:
- task_012_004_002
owners:
- swe
skills: []
parent_rev: 0db1197207201d59a851a4cc06e11d5680e70c0d
created: '2026-10-23'
updated: '2026-10-23'
---
# Emit one durable stall diagnostic and schedule one recovery

## Parent Feature

[feat_012_004](../../features/2_active/feat_012_004.md)

## Depends on

- task_012_004_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement episode-keyed, idempotent post-cancellation handling.

Acceptance:
- Emit exactly one durable diagnostic per unchanged stall episode.
- Include task/turn/provider identity, last-progress kind/time, elapsed duration, cancellation outcome, preserved-work state, and recovery disposition.
- Exclude prompts, credentials, and model output.
- Schedule at most one supervised recovery for the unchanged episode.
- Repeated polls/callbacks for that episode produce neither duplicate diagnostics nor duplicate recovery.
- New useful progress permits a new episode.
- Recovery uses the preserved checkpoint/worktree state and does not form a retry loop.
- Add focused tests for idempotency, redaction/data minimization, and new-episode behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
