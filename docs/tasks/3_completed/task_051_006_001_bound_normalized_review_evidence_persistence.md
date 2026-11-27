---
id: task_051_006_001
title: Bound normalized review evidence persistence
tier: task
status: completed
parent: feat_051_006
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 60392bd9d6cd38c1718af6ed27e4357aa7fa2322
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Bound normalized review evidence persistence

## Parent Feature

[feat_051_006](../../features/2_active/feat_051_006.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the lossless 32 KiB observation contract in cascade/review.py:record_feature_review_evidence, with 256 UTF-8 byte check-name and string-generation limits, 64 decimal-digit integer limit, 20-row presentation cap, and explicit omission. Oversized or malformed authoritative values must write a bounded unavailable marker when possible and return false so cascade/review_health.py:reconcile_open_review_health cannot classify green or admit repair. Keep exact names/generations; preserve zero. Cover boundary, over-limit, Unicode, same-prefix and persistence-failure paths in focused tests/test_review_health.py and tests/war_room/test_open_reviews_api.py. Review cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md and record diagram impact for cascade-watchdog-code and cascade-dashboard-code; leave model edits to integration task if this change does not add a significant symbol.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
