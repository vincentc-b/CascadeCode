---
id: task_032_001_001
title: Implement tier-scoped inventory-backed recovery dialog
tier: task
status: completed
parent: feat_032_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: eb1872821386e32f3de4a6713e8e44dec97c5b14
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Implement tier-scoped inventory-backed recovery dialog

## Parent Feature

[feat_032_001](../../features/2_active/feat_032_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Replace the free-text recovery input with a modal form that reuses the existing normalized provider inventory and brief selector primitives.

## Scope

- Render only the roles owned by the affected work tier: Epic Manager/Architect, Feature Lead/Architect, or SWE.
- Drive provider, model, optional reasoning, and flex controls from the normalized inventory.
- Revalidate dependent selections when provider or model changes.
- Preserve saved selections for display when they are no longer available, while treating them as invalid replacements.
- Handle loading, empty inventory, refresh failure, and cancel without losing the operator's current selections.
- Keep credentials and raw provider errors out of browser-visible state.

## Done when

The dialog exposes a valid complete replacement only when every affected role has a currently supported provider/model/reasoning/flex selection, and no static catalog or second discovery path is introduced.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
