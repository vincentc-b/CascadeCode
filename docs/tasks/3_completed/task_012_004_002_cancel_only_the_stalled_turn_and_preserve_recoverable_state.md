---
id: task_012_004_002
title: Cancel only the stalled turn and preserve recoverable state
tier: task
status: completed
parent: feat_012_004
children: []
depends_on:
- task_012_004_001
owners:
- swe
skills: []
parent_rev: 4725491d9bad13bd7abb1de7aa771f9d999aaae2
created: '2026-10-23'
updated: '2026-10-23'
---
# Cancel only the stalled turn and preserve recoverable state

## Parent Feature

[feat_012_004](../../features/2_active/feat_012_004.md)

## Depends on

- task_012_004_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Integrate stall expiry with the graceful turn-cancellation/draining seam delivered by feat_018_002.

Acceptance:
- Gate implementation on the feat_018_002 seam being present; reuse it without adding a parallel swe_turn/execution cancellation mechanism.
- On expiry, target only the affected turn's provider/bridge process tree.
- Bound escalation from graceful termination to targeted force-kill.
- Never terminate the supervisor, War Room, watchdog, or unrelated turns.
- Preserve the dirty task worktree and the last checkpoint/result evidence.
- Return a structured cancellation outcome and preserved-work state for downstream diagnostics.
- Add integration-level coverage for targeted process-tree cancellation and preservation.

Scope cuts:
- No whole-supervisor/War Room restart, broad process-name kill, or worktree cleanup/reset.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
