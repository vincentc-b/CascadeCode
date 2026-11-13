---
id: task_013_004_001
title: Prove stalled Feature and Epic work from authoritative observations
tier: task
status: completed
parent: feat_013_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2487adf14a7321cc3c174c608e61bc7554c6dd6a
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove stalled Feature and Epic work from authoritative observations

## Parent Feature

[feat_013_004](../../features/2_active/feat_013_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement parent-tier audit classification and repeat-observation evidence for owner absence, dispatchable children, stale inputs/graph and approval/comment/dependency gates, local integration awaiting publication, cancellation/return, and branch discrepancies. Use canonical expired lease/action deadlines where available; otherwise require unchanged authoritative observations across the configured interval. Keep live slow owners and expected human/review waits protected. Preserve split tracking/product repository identity. Acceptance: observations identify responsible work ID, generation, exact candidate action, and why it is executable or gated; no document-age-only stall proof. Add focused classification tests for both tiers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
