---
id: task_038_002_006
title: Verify stale-snapshot and sequential planning flows
tier: task
status: completed
parent: feat_038_002
children: []
depends_on:
- task_038_002_002
- task_038_002_003
- task_038_002_004
- task_038_002_005
owners:
- swe
skills: []
parent_rev: db76f641a4ba3cfdc19527762d9be83855d18e73
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify stale-snapshot and sequential planning flows

## Parent Feature

[feat_038_002](../../features/2_active/feat_038_002.md)

## Depends on

- task_038_002_002
- task_038_002_003
- task_038_002_004
- task_038_002_005

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend existing integration coverage for readiness, sign-off, minting, approval, and lifecycle actions. Exercise incomplete-to-complete and satisfied-to-unmet/unavailable changes after turn context creation with preloaded board cache/request snapshot. Assert refusal leaves no new sign-off, approval, or child. Cover sequential minting with unfinished valid predecessors, bulk epic-plan approval of sibling successors, successor dispatch refusal until prerequisites complete, and epic prerequisite failure leaving every child approval unchanged. Avoid redundant low-level tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
