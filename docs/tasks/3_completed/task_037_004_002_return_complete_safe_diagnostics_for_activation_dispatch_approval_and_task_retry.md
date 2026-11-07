---
id: task_037_004_002
title: Return complete safe diagnostics for activation, dispatch, approval and Task retry
tier: task
status: completed
parent: feat_037_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 39abd78e4e112d0da40b40ee9b20f80c78ae59da
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Return complete safe diagnostics for activation, dispatch, approval and Task retry

## Parent Feature

[feat_037_004](../../features/2_active/feat_037_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Unify War Room response serialization for Epic activation, Feature dispatch, approval-driven dispatch and Task retry with the shared evaluator's complete failed-role checks, selections, safe messages, configuration path/revision, freshness and valid remedies. Make partial approval/dispatch outcomes explicit (what was committed and what did not launch). Keep readable failure text primary; provider_preflight_blocked must never be the only feedback. Preserve error context after refusal and report an idempotent success once. Recheck current state at command boundaries so stale UI eligibility cannot grant authority. Add focused API tests for these response shapes and side-effect counts.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
