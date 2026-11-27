---
id: task_037_002_001
title: Validate complete role selections at brief and child configuration writes
tier: task
status: completed
parent: feat_037_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 5e9b0baf430778ea06265fbf49f7d6be0dae0969
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate complete role selections at brief and child configuration writes

## Parent Feature

[feat_037_002](../../features/2_active/feat_037_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement pre-persistence admission using the shared effective-selection evaluator for brief create/edit (all five Epic roles) and Feature/Task override introduction (Feature planning roles plus effective SWE, Task SWE). Resolve from the owning worktree; reject stale provenance, malformed/legacy resolution errors, and unsupported or transient capability without saving invalid changes. Preserve safe structured role results for callers. Add focused fixture tests for invalid future Feature/SWE roles and late child overrides. Use fake inventory; no provider turns.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
