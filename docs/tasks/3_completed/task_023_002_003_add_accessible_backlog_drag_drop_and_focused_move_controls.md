---
id: task_023_002_003
title: Add accessible backlog drag/drop and focused move controls
tier: task
status: completed
parent: feat_023_002
children: []
depends_on:
- task_023_002_002
owners:
- swe
skills: []
parent_rev: 6621913440ecf06db87f8054846bc54001b4625e
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add accessible backlog drag/drop and focused move controls

## Parent Feature

[feat_023_002](../../features/2_active/feat_023_002.md)

## Depends on

- task_023_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement backlog ordering interactions in the existing plain-JavaScript War Room board.

Scope:
- Render backlog feature cards in the canonical server order.
- Support drag/drop only among backlog peers within the same epic; dragging from row action controls must not invoke either a reorder or a row action accidentally.
- Provide clearly labelled non-drag controls to move the focused feature up/down, retaining useful focus after rerender.
- Submit the current concurrency token and intended complete order through the reorder command.
- Keep the optimistic/pending UI coherent with the 3-second board polling render. On failure or stale conflict, retain/restore the last server-confirmed order, show a clear error, and accept the newer order from the next/current response.
- Preserve selection, row actions, collapsed columns, return-to-backlog behavior, chat/sidebar behavior, and narrow-screen usability.

Verification:
- Extend the existing highest-signal browser/DOM test seam to cover drag ordering, focused up/down movement and focus retention, action-control isolation, success across refresh, and visible stale/error handling.
- Avoid a new test harness if current integration coverage can exercise these paths.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
