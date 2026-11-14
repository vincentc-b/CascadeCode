---
id: task_045_002_003
title: Render accessible New attention and verify corrective-feature browser journey
tier: task
status: completed
parent: feat_045_002
children: []
depends_on:
- task_045_002_002
owners:
- swe
skills: []
parent_rev: b9afd02b8b6040b5f2232a088a63ccc058666fdb
created: '2026-11-13'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Render accessible New attention and verify corrective-feature browser journey

## Parent Feature

[feat_045_002](../../features/2_active/feat_045_002.md)

## Depends on

- task_045_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add text New markers to feature board/review rows, separate from lifecycle and activation labels. Show accurate collapsed-Epic New counts with keyboard-operable reveal and plan navigation; explain workspace-shared Mark seen, provide explicit feature-level action, preserve focus and screen-reader labels, and show write failures. Maintain a client high-water attention revision so an older board poll cannot restore an acknowledged badge. Reuse the backend invariants. Prove in a real Chromium browser: an active Epic with a completed sibling gains two corrective features, aggregate reveals both, plans and approval needs are visible, each is marked seen, refresh/restart keeps badges gone, and completed sibling and approval remain unchanged.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
