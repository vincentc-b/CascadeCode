---
id: task_030_002_001
title: Implement lifecycle gate and locked eligibility recheck
tier: task
status: completed
parent: feat_030_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 93d22f6ba051fc922af29255138275ca736cb995
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Implement lifecycle gate and locked eligibility recheck

## Parent Feature

[feat_030_002](../../features/2_active/feat_030_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Add turn quiescence and a per-Epic lifecycle lock, then re-evaluate active-to-backlog eligibility while holding that lock.

## Scope
- Prevent new/racing turns from crossing the transition boundary.
- Wait for or safely reject non-quiescent active work according to the existing lifecycle contract.
- Serialize lifecycle transitions per Epic.
- Recheck eligibility after acquiring the lock so stale pre-lock observations cannot trigger a transition.

## Acceptance criteria
- Only one transition attempt per Epic can pass the lifecycle gate at a time.
- A request that becomes ineligible while waiting does not mutate durable state.
- Racing turns cannot create new active work after quiescence is established.
- Existing lifecycle behavior outside this transition remains unchanged.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
