---
id: task_038_001_004
title: Inject dependency projection into epic and feature planning turns
tier: task
status: completed
parent: feat_038_001
children: []
depends_on:
- task_038_001_003
owners:
- swe
skills: []
parent_rev: 855508b1a1a61e62bb0531bb8252408dc830a4b1
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Inject dependency projection into epic and feature planning turns

## Parent Feature

[feat_038_001](../../features/2_active/feat_038_001.md)

## Depends on

- task_038_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add the safe projection to every epic and feature planning turn using the caller's current owning spec as the declared dependency list. Preserve the existing prompt flow and scoped content authorization; a denied spec read remains content_access_denied independently of the status outcome. Add focused planning-turn integration coverage for both tiers, including completed unreadable dependencies, readable incomplete dependencies, all declared IDs, and no-dependency work.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
