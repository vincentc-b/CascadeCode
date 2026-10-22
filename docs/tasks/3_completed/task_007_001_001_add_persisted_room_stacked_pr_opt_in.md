---
id: task_007_001_001
title: Add persisted room stacked-PR opt-in
tier: task
status: completed
parent: feat_007_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 6a6fe88943f8adf8c97f436df82fef566d2664ab
created: '2026-10-22'
updated: '2026-10-22'
---
# Add persisted room stacked-PR opt-in

## Parent Feature

[feat_007_001](../../features/2_active/feat_007_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Add the minimal Cascade-room control and persistence for stacked pull requests.

## Scope
- Add a per-room stacked-PR boolean setting, defaulting to disabled for existing and new rooms.
- Expose it through the existing room settings API/state path and the smallest matching slider UI.
- Ensure toggling affects future eligibility reads only; do not mutate or retarget existing pull requests.
- Preserve compatibility for persisted rooms that lack the field.

## Acceptance
- Default is off when no value is stored.
- Setting survives reload/restart and remains isolated per room.
- Existing room-settings behavior remains intact.
- Focused integration coverage exercises default, persistence, and toggle behavior.

## Constraints
Follow existing settings patterns. Avoid new framework layers or broad UI redesign.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
