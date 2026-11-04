---
id: task_028_003_001
title: Render durable epic close-review state and controls in the War Room
tier: task
status: completed
parent: feat_028_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: a73db3bbb1b416c3bb236effec3b027815958aaf
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Render durable epic close-review state and controls in the War Room

## Parent Feature

[feat_028_003](../../features/2_active/feat_028_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Wire the persisted epic close stage into the Epic row beside the Close action.

## Acceptance criteria
- Pending close review shows the persisted stage and an accessible `Open implementation review` link.
- The link uses the existing safe external-link component and forge-provided text is rendered as text, never HTML.
- The state and link remain correct after refresh, navigation, and application restart because rendering is driven by persisted server state.
- When automatic reconciliation cannot run, an actionable `Finish close` control is available.
- Ambiguous status is replaced with actionable blocker details.
- Successful completion updates the row to the completed close state.

## Scope constraints
Reuse existing API/state contracts from the preceding close-review persistence feature where possible; make only the smallest contract adaptation required for this UI.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
