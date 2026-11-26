---
id: task_044_003_003
title: Add paginated audit history and single-flight refresh
tier: task
status: completed
parent: feat_044_003
children: []
depends_on:
- task_044_003_002
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
# Add paginated audit history and single-flight refresh

## Parent Feature

[feat_044_003](../../features/2_active/feat_044_003_present_actionable_health_coverage_and_retained_recovery_history.md)

## Depends on

task_044_003_002.

## Acceptance criteria

- History is collapsed by default and fetches only on opening. Applied filters cover exact work ID, owner, verification status and UTC occurrence bounds; pages use the API's opaque next_cursor with unchanged filters and epoch.
- A 409/epoch change visibly restarts the page flow; old in-flight responses cannot overwrite a new filter or epoch. Show continuation/reason when reads are incomplete and keep rendered rows bounded.
- Each history row distinguishes occurred_at from last_attempted_at and last_verified_at and preserves source_ref, legacy provenance and unverifiable/previous-attempt wording.
- Visible-tab five-second status refresh is single-flight, avoids overlapping detail-page requests and does not issue POST. Disclosure/filter state survives ordinary status refresh.

## Files likely touched

- cascade/war_room/static/audit_status_ui.js
- cascade/war_room/static/war_room.js
- cascade/war_room/static/war_room.css
- cascade/war_room/templates/war_room.html
- tests/war_room/audit_status_ui_cases.mjs
- tests/war_room/war_room_refresh_races.mjs

## Implementation notes

Use existing GET /api/health/audit/history and its server-side limit/cursor contract. Keep history status filtering labeled as verification status, not raw recovery outcome. Use textContent for all evidence and provenance strings.

## Skills

None beyond SWE role defaults.

## Test plan

Run focused Node UI and refresh-race harnesses. Simulate slow first response, multiple visible tabs/refreshes, rapid filter changes, 409 restart, malformed/legacy rows and no duplicate page or POST activity.

## Out of scope

History deletion/compaction, GET reassessment and recovery dispatch.
