---
id: task_013_001_005
title: Define locked fresh-recheck and crash-safe reservation interfaces
tier: task
status: completed
parent: feat_013_001
children: []
depends_on:
- task_013_001_003
- task_013_001_004
owners:
- swe
skills: []
parent_rev: e42512edf87a275dc4c15513cf66b40350b9ad28
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define locked fresh-recheck and crash-safe reservation interfaces

## Parent Feature

[feat_013_001](../../features/2_active/feat_013_001.md)

## Depends on

- task_013_001_003
- task_013_001_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Provide the shared observation-to-mutation boundary used by later repair adapters. A selected incident is re-read under its owning lifecycle lock, checked against typed identity and authoritative generation, then reserved with a bounded claim before any existing lifecycle operation may run.

## Acceptance
- Lock ordering is canonical and broad locks are released before provider, network, Git, or test I/O.
- A disappeared or changed incident yields a no-op without lifecycle mutation; a concurrent manual recovery cannot cause duplicate action.
- Claim leases expire; interrupted request/acknowledgement/result sequences replay or roll back safely and preserve history.
- No repair adapter or scheduler is implemented in this feature; the interface is ready for later features to invoke existing operations.

## Validation
Exercise changed preconditions, concurrent claim/manual recovery, interrupted claim, and typed Feature ID versus parent_rev.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
