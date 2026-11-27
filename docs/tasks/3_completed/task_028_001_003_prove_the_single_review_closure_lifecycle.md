---
id: task_028_001_003
title: Prove the single-review closure lifecycle
tier: task
status: completed
parent: feat_028_001
children: []
depends_on:
- task_028_001_002
owners:
- swe
skills: []
parent_rev: d8939ce0926a2e7a4cf0315ab36b7dbb7a8af79f
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Prove the single-review closure lifecycle

## Parent Feature

[feat_028_001](../../features/2_active/feat_028_001.md)

## Depends on

- task_028_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal lifecycle-level coverage for preparation idempotency, open-review pending state, remote-trunk verification blockers, successful post-merge reconciliation, untouched operator checkout, and the invariant that no second terminal-only PR is created. Reuse existing lower-level coverage rather than duplicating it.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
