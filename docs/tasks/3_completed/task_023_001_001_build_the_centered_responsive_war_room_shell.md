---
id: task_023_001_001
title: Build the centered responsive War Room shell
tier: task
status: completed
parent: feat_023_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 14c0274b82af7251c1a90723620a8e0141d09126
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Build the centered responsive War Room shell

## Parent Feature

[feat_023_001](../../features/2_active/feat_023_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement the feature's foundational layout without changing existing War Room behavior.

## Scope

- Arrange context on the left, the board in the center, and utilities on the right at wide viewports.
- Use the available viewport while keeping the board's width stable across polling/data rerenders.
- Provide a usable narrow-screen reflow for the same regions.
- Preserve board actions, lens, chat, and sidebar behavior.
- Add focused layout/regression coverage at representative wide and narrow viewports, including a polling rerender.

## Acceptance criteria

- Wide layouts are centered and retain the specified left/center/right hierarchy.
- The board does not shift width solely because polled content changes.
- Narrow layouts remain operable without hiding required behavior.
- Existing War Room interactions continue to work.
- High-signal tests cover responsive placement and width stability.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
