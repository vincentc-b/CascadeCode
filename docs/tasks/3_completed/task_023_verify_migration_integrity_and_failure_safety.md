---
id: task_023
title: Verify migration integrity and failure safety
tier: task
status: completed
parent: feat_010
children: []
depends_on:
- task_022
owners:
- swe
skills: []
parent_rev: 46c0e93179972a8d425044686910ab46a630d00b
created: '2026-10-22'
updated: '2026-10-22'
---
# Verify migration integrity and failure safety

## Parent Feature

[feat_010](../../features/2_active/feat_010.md)

## Depends on

- task_022

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add focused integration coverage around the public migration workflow. Cover successful renumbering of multiple backlog epics with nested feature/task descendants and cross-document board references; prove active/completed work remains byte-for-byte or semantically unchanged as appropriate; and cover collision, malformed-reference, and injected apply failure cases with zero partial mutation. Prefer fixture-level integration tests over redundant mock-heavy unit tests. Acceptance: tests verify hierarchy, referential integrity, deterministic mappings, idempotent/no-op behavior when nothing is eligible, and rollback/fail-safe guarantees.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
