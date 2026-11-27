---
id: task_013_005_001
title: Expose durable audit status and incidents in the War Room
tier: task
status: completed
parent: feat_013_005
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: f564adede2d63d861f4db2424431a82df1cc3a3d
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose durable audit status and incidents in the War Room

## Parent Feature

[feat_013_005](../../features/2_active/feat_013_005.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Project the compact audit receipt and existing durable incident state into a read-only War Room payload. Render last run, next due, duration, counts by tier/outcome, and active incidents with concrete owner, evidence, request/acknowledgement/result, retry/cooldown, and exact resume action. Preserve truthful pending/acknowledged states and show unavailable evidence explicitly. Use the existing route/JavaScript harness to verify displayed state matches durable state.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
