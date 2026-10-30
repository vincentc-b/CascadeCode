---
id: task_012_002_001
title: Implement bounded convergence-state detection
tier: task
status: completed
parent: feat_012_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 87e25c54c4ac798175399a62184d316494d5fc2b
created: '2026-10-23'
updated: '2026-10-23'
---
# Implement bounded convergence-state detection

## Parent Feature

[feat_012_002](../../features/2_active/feat_012_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement read-only convergence detection for approved features and dependency-ready tasks using the existing Boss View/dispatch readiness predicates.

## Scope

- Reuse authoritative readiness and dispatch eligibility logic; do not duplicate or approximate it.
- Derive progress from durable board, queue, cursor, and lifecycle evidence.
- Add an explicit bounded threshold and injected clock.
- Report stalled, progressing, gated, and recovered state without dispatching or mutating live work.

## Acceptance

- Eligible items become stalled only after the configured threshold without relevant durable progress.
- Gated or ineligible items are not reported as stalled.
- New durable progress and recovery reset or clear stall state.
- Process liveness alone does not count as progress.
- Detection remains read-only and cannot create or dispatch work.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
