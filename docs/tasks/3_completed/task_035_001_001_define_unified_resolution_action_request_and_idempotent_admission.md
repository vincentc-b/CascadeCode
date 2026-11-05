---
id: task_035_001_001
title: Define unified resolution-action request and idempotent admission
tier: task
status: completed
parent: feat_035_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 38e374635ecd12a2f19223a90296324969d67dda
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Define unified resolution-action request and idempotent admission

## Parent Feature

[feat_035_001](../../features/2_active/feat_035_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement one durable resolution-action request contract shared by explicit operator requests and epic_031 recovery requests.

## Acceptance criteria

- Both entry paths normalize into the same request type.
- The idempotency key is derived from stable action identity fields and duplicate admission returns/reuses the existing action.
- Required review, ref, source-head, and requester/assignment metadata is validated without performing mutation.
- Contract and identity behavior are covered by focused tests.

## Non-goals

No review mutation, rebase, conflict editing, push, or lifecycle-gate bypass.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
