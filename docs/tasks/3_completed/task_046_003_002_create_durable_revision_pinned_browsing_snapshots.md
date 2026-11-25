---
id: task_046_003_002
title: Create durable revision-pinned browsing snapshots
tier: task
status: completed
parent: feat_046_003
children: []
depends_on:
- task_046_003_001
owners:
- swe
skills: []
parent_rev: 88793bda1f8a5edde89ffc70211195637aeabef4
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Create durable revision-pinned browsing snapshots

## Parent Feature

[feat_046_003](../../features/2_active/feat_046_003.md)

## Depends on

- task_046_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement immutable snapshot identity for known context, full code and documentation commits, destination/mapping revision, association provenance, source closure and render identity. Read model/document bytes from commits, excluding dirty edits. Reuse production C4 source validation, bounded shared render scheduler/cache, semantic binding and safe artifact contracts; opening or refreshing the board must not rerender identical evidence. Persist descriptors so reload and server restart recover the same snapshot; missing commits, model, deeper views, render failure and oversized artifacts return explicit states. Compare selected branch HEAD cheaply and create a new whole snapshot only on explicit refresh. Browsing must not create review units or acceptance. Focused service tests cover pinning, HEAD advance, cache reuse, restart and failure states.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
