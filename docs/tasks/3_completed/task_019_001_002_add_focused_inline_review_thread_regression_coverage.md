---
id: task_019_001_002
title: Add focused inline review-thread regression coverage
tier: task
status: completed
parent: feat_019_001
children: []
depends_on:
- task_019_001_001
owners:
- swe
skills: []
parent_rev: 6c7a79bf70f2e6c957204098846957c2438ec92d
created: '2026-10-22'
updated: '2026-10-23'
---
# Add focused inline review-thread regression coverage

## Parent Feature

[feat_019_001](../../features/2_active/feat_019_001.md)

## Depends on

- task_019_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add focused, high-signal UI regression coverage for feat_019_001 after the inline rendering implementation lands.

Cover:
- Resolvable anchored roots render inline on both epic and feature initial load.
- A successful post/refresh and polling reconciliation produce exactly one inline root without reload.
- Repeated renders neither duplicate nor reorder threads.
- Multiple roots on one block retain API order.
- Whole-plan, invalid, missing, and unplaceable outdated anchors render once in the tray.
- Relocatable outdated anchors remain inline and visibly outdated.
- Reply and resolve update an inline thread in place while unrelated reply drafts survive reconciliation.
- Task pages keep their current layout.
- Inline controls remain keyboard reachable, existing live-region announcements fire, and supported narrow widths do not horizontally scroll.

Favor existing viewer/integration test seams over duplicating lower-level API and lifecycle tests. Run focused epic/feature UI tests plus the existing comment API/lifecycle suite required by the feature acceptance criteria; report failures with enough detail to distinguish regressions from environment issues.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
