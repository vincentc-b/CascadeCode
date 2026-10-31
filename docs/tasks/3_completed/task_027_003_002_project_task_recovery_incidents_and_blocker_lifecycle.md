---
id: task_027_003_002
title: Project Task recovery incidents and blocker lifecycle
tier: task
status: completed
parent: feat_027_003
children: []
depends_on:
- task_027_003_001
owners:
- swe
skills: []
parent_rev: ebaa4bba43f2a63bb0492a08d4cfe39d67b2ca90
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Project Task recovery incidents and blocker lifecycle

## Parent Feature

[feat_027_003](../../features/2_active/feat_027_003.md)

## Depends on

- task_027_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Surface recovery state and incidents through existing War Room state and parent blockage provenance, including semantic merge conflicts. Render the precise recovery outcome from the shared operation, create or retain the correctly attributed derived blocker when recovery remains blocked, and clear only the blocker derived from the matching recovery incident when it is resolved. Do not disturb unrelated blockers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
