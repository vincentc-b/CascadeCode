---
id: task_023_001_002
title: Add accessible panel resizing, persistence, and reset
tier: task
status: completed
parent: feat_023_001
children: []
depends_on:
- task_023_001_001
owners:
- swe
skills: []
parent_rev: ac487980736a4c902820f0c6c10ec99b09392028
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add accessible panel resizing, persistence, and reset

## Parent Feature

[feat_023_001](../../features/2_active/feat_023_001.md)

## Depends on

- task_023_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add user-controlled panel sizing to the responsive shell, with safe browser-local persistence and an accessible reset path.

## Scope

- Add resize controls for the applicable War Room side panels.
- Clamp sizes so the board and controls remain usable at supported viewport widths.
- Persist valid sizes in this browser and restore them without introducing layout shifts during polling.
- Handle missing, stale, or invalid stored values by falling back to defaults.
- Provide a clearly discoverable reset to default sizes.
- Make resize and reset controls keyboard accessible and expose appropriate semantics.
- Add focused interaction coverage for clamping, persistence/restore, reset, and keyboard operation.

## Acceptance criteria

- Pointer and keyboard users can resize panels within enforced bounds.
- Reloading restores valid saved sizes from browser-local storage.
- Reset clears the saved customization and restores defaults.
- Invalid persisted data cannot break the layout.
- Narrow layouts remain usable and existing board, lens, chat, and sidebar interactions still work.
- High-signal tests cover the complete resize/persist/reset flow.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
