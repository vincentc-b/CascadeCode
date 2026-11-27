---
id: task_044_003_002
title: Render verified blockers and grouped coverage in Health audit
tier: task
status: completed
parent: feat_044_003
children: []
depends_on:
- task_044_003_001
owners:
- swe
skills: []
parent_rev: 667cfc75045946a1779a0e52f6d4601be9508401
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Render verified blockers and grouped coverage in Health audit

## Parent Feature

[feat_044_003](../../features/2_active/feat_044_003_present_actionable_health_coverage_and_retained_recovery_history.md)

## Depends on

task_044_003_001.

## Acceptance criteria

- Schema-2 current rows are prominent and show work, owner, failure class/impact, occurrence, last attempted/verified times, freshness, source reference and next attempt/action where available; a partial current page shows continuation.
- One aggregate coverage summary reports pending, stale and unverifiable counts, last completed/next scheduled check and explicit pending snapshot/failure state. An accessible disclosure fetches bounded coverage pages only when opened and groups repeated work IDs or reasons while preserving per-record source references.
- Zero verified rows with incomplete current pagination, incomplete coverage or pending/stale snapshot reads exactly as no VERIFIED current incidents with incomplete coverage.
- Investigation request, delivery, acknowledgement and reported_fixed are visibly separate from verified incident/resolution status. All external strings use safe DOM text nodes; controls work by keyboard and on narrow layouts.

## Files likely touched

- cascade/war_room/static/audit_status_ui.js
- cascade/war_room/static/war_room.css
- cascade/war_room/templates/war_room.html
- tests/war_room/audit_status_ui_cases.mjs

## Implementation notes

Consume the API contract in the parent Feature and task 001's bounded follow-up summary. Do not rely on the legacy incidents alias for authority. Keep coverage detail loading on disclosure and cap rendered rows to each returned page.

## Skills

None beyond SWE role defaults.

## Test plan

Run the focused Node UI harness through tests/war_room/test_audit_status_ui.py. Include a later current blocker amid older failures, a partial current page, pending/corrupt snapshots, grouped coverage details, follow-up status separation and untrusted markup.

## Out of scope

Recovery policy, source ledger changes, frontend framework and full history UI.
