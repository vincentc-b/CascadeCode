---
id: task_035_002_002
title: Execute guarded owned-source rebase and conflict resolution
tier: task
status: completed
parent: feat_035_002
children: []
depends_on:
- task_035_002_001
owners:
- swe
skills: []
parent_rev: f15627b1a9c50f00153e41c438a26b1a773efad3
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Execute guarded owned-source rebase and conflict resolution

## Parent Feature

[feat_035_002](../../features/2_active/feat_035_002.md)

## Depends on

- task_035_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Rebase the admitted owned source branch onto the validated target. Restrict edits to conflicted paths that are also owned/authorized, reject unrelated mutations, and stop with preserved state when conflicts require an unresolved product or semantic decision. Never rewrite the target/trunk, create or replace reviews, or bypass lifecycle/review gates. Add high-signal tests for path restrictions and ambiguity handling.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
