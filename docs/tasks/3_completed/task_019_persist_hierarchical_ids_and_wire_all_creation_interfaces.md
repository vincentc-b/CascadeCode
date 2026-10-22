---
id: task_019
title: Persist hierarchical IDs and wire all creation interfaces
tier: task
status: completed
parent: feat_009
children: []
depends_on:
- task_018
owners:
- swe
skills: []
parent_rev: 63309caaa5e1f35ef098602dbdbdb3f18f055ddf
created: '2026-10-22'
updated: '2026-10-22'
---
# Persist hierarchical IDs and wire all creation interfaces

## Parent Feature

[feat_009](../../features/2_active/feat_009.md)

## Depends on

- task_018

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Integrate the canonical allocator and validator into persistence and every epic, feature, and task creation path. Ensure assigned IDs round-trip unchanged, parent relationships use the canonical IDs, collision failures surface clearly, and pre-existing non-backlog identifiers remain readable and unaffected. Add integration coverage at the persistence/interface boundary.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
