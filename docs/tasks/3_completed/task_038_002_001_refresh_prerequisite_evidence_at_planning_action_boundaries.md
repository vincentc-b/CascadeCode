---
id: task_038_002_001
title: Refresh prerequisite evidence at planning action boundaries
tier: task
status: completed
parent: feat_038_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 21578e9c09788170b2191eb52adf97c7964e4ca7
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Refresh prerequisite evidence at planning action boundaries

## Parent Feature

[feat_038_002](../../features/2_active/feat_038_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement a reusable action-boundary check for the owning work item's current declared dependencies and authoritative lifecycle evidence, consuming the shared evaluator/status contract from feat_038_001. Run inside existing action/lifecycle synchronization or use a minimal revision-checked retry/refusal. A failed refresh returns dependency_status_unavailable; known unmet prerequisites return dependency_unmet. Keep dependency evidence separate from plan revision and body-read authorization. No authorization-dependent mutation may commit after superseding evidence.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
