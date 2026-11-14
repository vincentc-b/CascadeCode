---
id: task_044_003_001
title: Publish bounded audit investigation follow-up summaries
tier: task
status: completed
parent: feat_044_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 008581f565a88f45a7f3bcd09643a121626a9dfc
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Publish bounded audit investigation follow-up summaries

## Parent Feature

[feat_044_003](../../features/2_active/feat_044_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Acceptance: The audit producer or investigation lane publishes a compact, versioned, timestamped follow-up snapshot from durable investigation cases; GET /api/health/audit exposes bounded request, delivery/acknowledgement, latest report outcome/finding/reference and pending reassessment state without walking case files, board, Git, providers or lifecycle state. Include source identity and an explicit unavailable/truncated state; missing/corrupt follow-up evidence stays pending. Request delivery, acknowledgement and reported_fixed are never mapped to verified resolution. Preserve product/tracking root routing, existing case files and human/repair gates. Files likely touched: cascade/watchdog/audit_investigation.py, cascade/watchdog/audit_agent_lane.py or audit_projection.py, cascade/war_room/audit_status.py, focused tests under tests/watchdog and tests/war_room. Test with delivered, acknowledged, reported_fixed, malformed/missing and split-root cases; assert concurrent GETs are read-only and bounded. Out of scope: recovery policy, source-ledger migration, new scheduler/service, approval bypass.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
