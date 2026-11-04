---
id: task_035_001_003
title: Enforce admission safety gates and persist actionable blocker state
tier: task
status: completed
parent: feat_035_001
children: []
depends_on:
- task_035_001_001
- task_035_001_002
owners:
- swe
skills: []
parent_rev: 0459d70ab5b68e790d813b2440b0d5783f86bcae
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Enforce admission safety gates and persist actionable blocker state

## Parent Feature

[feat_035_001](../../features/2_active/feat_035_001.md)

## Depends on

- task_035_001_001
- task_035_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Prevent unsafe resolution actions from reaching mutation and persist enough War Room state for an operator to resume safely.

## Acceptance criteria

- Admission rejects closed reviews, unauthorized refs, stale observed heads, dirty unrelated paths, missing metadata, unavailable credentials, and insufficient permissions.
- Checks use only the scoped inspection surface from context resolution.
- Every rejection records the failed checkpoint, observed refs and SHAs, affected paths when applicable, and a concrete resume action.
- Successful admission produces a mutation-ready handoff but performs no mutation.
- Boundary behavior is covered by focused tests.

## Non-goals

No rebase, conflict edits, force-with-lease push, general shell, or lifecycle-gate bypass.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
