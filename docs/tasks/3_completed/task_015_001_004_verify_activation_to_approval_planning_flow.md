---
id: task_015_001_004
title: Verify activation-to-approval planning flow
tier: task
status: completed
parent: feat_015_001
children: []
depends_on:
- task_015_001_003
owners:
- swe
skills: []
parent_rev: 827bbdb8fe96ddd3dba983f72a724630fad3a27f
created: '2026-10-23'
updated: '2026-10-23'
---
# Verify activation-to-approval planning flow

## Parent Feature

[feat_015_001](../../features/2_active/feat_015_001.md)

## Depends on

- task_015_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add one integration flow proving the authoritative planning gate from epic activation through approval.

## Scenarios

- Newly activated epic cannot be approved.
- One role sign-off remains insufficient.
- An unresolved canonical question blocks either sign-off.
- Both roles signing the current revision with no unresolved questions permit approval.
- A material revision invalidates readiness from prior sign-offs.
- Direct and stale-client approval attempts are rejected.
- Existing approved records remain approved across the new behavior.

## Verification approach

Prefer one table-driven integration/API flow that asserts both command outcomes and the public read model. Add lower-level tests only where the integration flow cannot economically cover persistence compatibility or idempotency.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
