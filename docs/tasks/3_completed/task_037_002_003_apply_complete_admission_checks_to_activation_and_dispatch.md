---
id: task_037_002_003
title: Apply complete admission checks to activation and dispatch
tier: task
status: completed
parent: feat_037_002
children: []
depends_on:
- task_037_002_001
- task_037_002_002
owners:
- swe
skills: []
parent_rev: 2e851f651db32f7ec9b7c1271242a2a803da4d39
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Apply complete admission checks to activation and dispatch

## Parent Feature

[feat_037_002](../../features/2_active/feat_037_002.md)

## Depends on

- task_037_002_001
- task_037_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the same shared admission checks in manual and automated Epic activation, Feature dispatch, and Task dispatch/retry. Epic must check all five roles; Feature checks planning roles plus effective SWE; Task checks SWE. Resolve owning-worktree documents and reject stale provenance. Run checks before lifecycle events, worktree creation, queue writes, approval/checkpoint advancement, or model-turn accounting. Deterministic refusals leave those effects unchanged; transient failures fail closed with bounded retry/setup remedies. Preserve the full structured batch in dispatch responses. Add representative manual/automatic integration tests using fake inventory/process boundaries.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
