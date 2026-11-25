---
id: task_047_002_001
title: Persist repair generation and authorize exact Feature reactivation
tier: task
status: completed
parent: feat_047_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 5436a088addcbb9a4b6913b1ce8e9481448e0d74
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist repair generation and authorize exact Feature reactivation

## Parent Feature

[feat_047_002](../../features/2_active/feat_047_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the generation-bound feature_repair action, scoped admission/resume and dedicated FeatureRepairAuthorized event; make Watchdog recognize only the exact fenced active introduction. See parent Feature API and diagram inventory. Preserve all action attempts and refuse stale ownership, approvals, live leases and mismatched authority.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
