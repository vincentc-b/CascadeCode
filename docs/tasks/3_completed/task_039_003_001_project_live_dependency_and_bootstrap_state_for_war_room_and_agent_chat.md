---
id: task_039_003_001
title: Project live dependency and bootstrap state for War Room and agent chat
tier: task
status: completed
parent: feat_039_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 6d411bd83bf232d480083a57a2dc98503cc1c967
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Project live dependency and bootstrap state for War Room and agent chat

## Parent Feature

[feat_039_003](../../features/2_active/feat_039_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build one read model from the canonical manifest, bootstrap scope/blockers, per-entry installation approvals, attempts, evidence, and planning readiness. Expose status, responsible actor, actual environment, last check/output, actionable failure, why needed, exact safe investigation or pinned setup guidance where known, expected verification, owned-artifact cleanup, and missing/current/stale approval for the complete binding. Keep unknown recipe facts explicit and preserve mismatch visibility. Feed both existing War Room read routes and agent chat summaries from this projection; no duplicate authority store or general dependency dashboard. Verify current-state projection for blocked, stale, ready, and explicit empty-manifest cases.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
