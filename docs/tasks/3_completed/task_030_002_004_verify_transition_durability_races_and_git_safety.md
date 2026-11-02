---
id: task_030_002_004
title: Verify transition durability, races, and Git safety
tier: task
status: completed
parent: feat_030_002
children: []
depends_on:
- task_030_002_003
owners:
- swe
skills: []
parent_rev: 3888fd3c4f3565ab9df90f66cbc88cd62f068782
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Verify transition durability, races, and Git safety

## Parent Feature

[feat_030_002](../../features/2_active/feat_030_002.md)

## Depends on

- task_030_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Add economical, high-signal integration coverage for the complete active-to-backlog lifecycle.

## Scope
Exercise the transition through public/service boundaries rather than duplicating low-level unit coverage:
- concurrent and repeated transition requests;
- restart/fault injection at every durable journal boundary;
- turns racing quiescence and locked eligibility recheck;
- Git safety refusals;
- preservation/restoration/removal/invalidation outcomes;
- deduplicated audit output;
- proof that operator trunk is not mutated.

## Acceptance criteria
- Tests deterministically cover every listed scenario and fail on partial or duplicate transitions.
- Restart cases demonstrate convergence from each durable boundary.
- Race tests demonstrate serialization and stale-run rejection.
- The suite remains focused on behavior and avoids redundant mock-heavy tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
