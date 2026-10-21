---
id: task_009
title: Build disposable lifecycle scenario setup
tier: task
status: completed
parent: feat_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2662c911ad6e18baeb2a1c31f1f08f58080f4490
created: '2026-10-21'
updated: '2026-10-21'
---
# Build disposable lifecycle scenario setup

## Parent Feature

[feat_004](../../features/2_active/feat_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Create the minimal reusable fixture/setup in the existing browser/system harness (Playwright where supported). Seed the feature lifecycle state needed to exercise approval and dependency gating through existing public entry points. Keep all data disposable and avoid introducing a new test framework.

Acceptance:
- Scenario starts from deterministic disposable state.
- Blocked work can be observed as undispatched.
- Setup supports completing the dependency and subsequent lifecycle steps.
- Repeated setup/cleanup is safe for local and CI execution.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
