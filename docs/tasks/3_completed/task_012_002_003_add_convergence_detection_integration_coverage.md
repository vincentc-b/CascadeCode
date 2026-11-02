---
id: task_012_002_003
title: Add convergence detection integration coverage
tier: task
status: completed
parent: feat_012_002
children: []
depends_on:
- task_012_002_001
- task_012_002_002
owners:
- swe
skills: []
parent_rev: 87e25c54c4ac798175399a62184d316494d5fc2b
created: '2026-10-23'
updated: '2026-10-23'
---
# Add convergence detection integration coverage

## Parent Feature

[feat_012_002](../../features/2_active/feat_012_002.md)

## Depends on

- task_012_002_001
- task_012_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add high-signal integration coverage for convergence detection and its durable diagnostics.

## Scenarios

- An eligible item with no relevant progress crosses the injected-clock threshold and emits one diagnostic.
- Durable board, queue, cursor, or lifecycle progress prevents or resets a stall.
- A gated item is excluded by the authoritative readiness predicate.
- An item recovers, then can be diagnosed again after a distinct later stall.
- Repeated polls with unchanged evidence remain deduplicated.
- Detection never dispatches, bypasses gates, or creates duplicate work.

## Acceptance

- Tests exercise the production readiness/dispatch predicate path and durable event/toast stream.
- Time is deterministic through the injected clock.
- Coverage favors integration behavior over redundant mock-heavy unit tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
