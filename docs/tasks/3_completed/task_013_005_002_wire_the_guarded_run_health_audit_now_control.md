---
id: task_013_005_002
title: Wire the guarded Run health audit now control
tier: task
status: completed
parent: feat_013_005
children: []
depends_on:
- task_013_005_001
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
# Wire the guarded Run health audit now control

## Parent Feature

[feat_013_005](../../features/2_active/feat_013_005.md)

## Depends on

- task_013_005_001

## Acceptance criteria

1. Render a guarded Run health audit now control using the existing authenticated human request path and empty-body POST /api/health/audit.
2. Show admitted, coalesced and unavailable responses accurately; disable duplicate submission while pending. Admission is not terminal recovery.
3. Manual execution works when scheduling is disabled, coalesces with scheduled/manual work through the shared coordinator, and leaves the periodic deadline unchanged.

## Files likely touched

`cascade/war_room/health_routes.py`, `cascade/war_room/static/war_room.js`, War Room markup/style, `tests/war_room/test_health_audit_routes.py` and focused UI cases.

## Implementation notes

Add the War Room control to invoke the existing authenticated POST /api/health/audit route and shared coordinator. Show admitted/coalesced/unavailable responses, prevent duplicate UI submissions, and verify scheduled/manual coalescing, unchanged periodic deadline, and explicit manual operation while scheduled auditing is disabled. Reuse existing human request protections; no new authority path.

## Skills

_(none)_

## Test plan

Run the route and JavaScript harness for authentication, duplicate requests, unavailable/stopped coordinator, disabled scheduling and unchanged due time.

## Out of scope

No direct repair endpoint, new authority path or schedule reset.
