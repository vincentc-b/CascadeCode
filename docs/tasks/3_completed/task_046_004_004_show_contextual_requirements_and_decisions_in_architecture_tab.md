---
id: task_046_004_004
title: Show contextual requirements and decisions in Architecture tab
tier: task
status: completed
parent: feat_046_004
children: []
depends_on:
- task_046_004_002
owners:
- swe
skills: []
parent_rev: 59db366f91d7d864e1c45b30f3f16d052a4d8fa7
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Show contextual requirements and decisions in Architecture tab

## Parent Feature

[feat_046_004](../../features/2_active/feat_046_004.md)

## Depends on

- task_046_004_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add the lazy Requirements & decisions panel to branch Architecture browsing. Update it with the selected pinned snapshot, view, and target; show explicit links and owning designs, view links plus a labeled broader index with no target selected, and clear unmapped/missing/stale states. Open source sections and full documents from the selected snapshot or recorded cross-repository documentation association. Ensure branch/ref switching changes diagram and context together and never reads tracking HEAD as a substitute.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
