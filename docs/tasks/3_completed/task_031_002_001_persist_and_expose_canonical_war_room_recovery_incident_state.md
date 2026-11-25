---
id: task_031_002_001
title: Persist and expose canonical War Room recovery incident state
tier: task
status: completed
parent: feat_031_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 3803382fbcc74401852e8b9c5541c4115ac1961f
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Persist and expose canonical War Room recovery incident state

## Parent Feature

[feat_031_002](../../features/2_active/feat_031_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement the durable board/API recovery-state projection for an affected War Room row from first failure through resolution or a human blocker.

## Scope

- Define the minimal canonical recovery incident fields: exact state, failure-specific safe reason, owner, affected branch or paths, last attempt, and action/review target.
- Persist and rehydrate the state across refreshes and service restarts using the existing board model.
- Transition to “investigating” only after the team request is durably queued.
- Clear the active incident projection on resolution.
- Preserve existing API compatibility where practical.

## Acceptance

- API/board reads return the same active incident after refresh or restart.
- State transitions are exact and never claim queued investigation prematurely.
- Blocked state includes owner and concrete next step/action target.
- Resolution removes the active warning state.
- Add focused contract/integration coverage for persistence and transitions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
