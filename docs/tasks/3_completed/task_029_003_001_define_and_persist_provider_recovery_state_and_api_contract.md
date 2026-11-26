---
id: task_029_003_001
title: Define and persist provider-recovery state and API contract
tier: task
status: completed
parent: feat_029_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2fae02f2bc0a1be42fae4a50e1e0a9e174476035
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Define and persist provider-recovery state and API contract

## Parent Feature

[feat_029_003](../../features/2_active/feat_029_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Implement the durable provider blocker/recovery state shared by board and War Room, including a safe human-readable reason.

## Scope
- Model activation failure, post-start provider loss, restored credentials, stale provider/model pins, and non-stoppable turns.
- Define API response/action contracts for Change provider, Retry, provider setup guidance, and eligible Return to backlog.
- Keep provider setup and Return to backlog as distinct states/actions.
- Preserve recovery state across restart and avoid mutating unaffected siblings or children.

## Acceptance criteria
- Recovery state and safe reason are durable and consistently serialized.
- Action eligibility is explicit for active Epic, active Feature, clean/dirty Task, and non-stoppable turn states.
- Existing unaffected work behavior remains unchanged.
- Focused contract/persistence tests cover the core state transitions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
