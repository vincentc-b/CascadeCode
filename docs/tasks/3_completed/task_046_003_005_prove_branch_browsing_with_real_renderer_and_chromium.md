---
id: task_046_003_005
title: Prove branch browsing with real renderer and Chromium
tier: task
status: completed
parent: feat_046_003
children: []
depends_on:
- task_046_003_004
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
# Prove branch browsing with real renderer and Chromium

## Parent Feature

[feat_046_003](../../features/2_active/feat_046_003.md)

## Depends on

- task_046_003_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend the shared real planning/renderer/browser fixture and use running War Room routes with actual versioned C4 artifacts. Verify default session worktree, view/level selection, relationship detail, drill/back, pan/zoom/fit, readable pinned source and deep-link reload. Switch to a second known branch with a deliberately different model; advance HEAD and prove the old snapshot remains coherent until explicit refresh. Exercise detached HEAD, dirty edits excluded from committed content, missing model/deeper view, pending/failed render with responsive tab and repeated board refresh cache reuse. Cover split code/document refs with exact association and explicit missing-association selection. Retain focused API assertions for authorization and pinning; do not fabricate diagram payloads or substitute DOM-only tests for the browser journey.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
