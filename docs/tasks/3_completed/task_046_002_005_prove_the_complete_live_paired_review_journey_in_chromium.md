---
id: task_046_002_005
title: Prove the complete live paired-review journey in Chromium
tier: task
status: completed
parent: feat_046_002
children: []
depends_on:
- task_046_002_003
- task_046_002_004
owners:
- swe
skills: []
parent_rev: c56b95900e11c7c1174d35d7c1af1b8fccec142f
created: '2026-11-10'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove the complete live paired-review journey in Chromium

## Parent Feature

[feat_046_002](../../features/2_active/feat_046_002.md)

## Depends on

- task_046_002_003
- task_046_002_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend the existing real planning/renderer/browser journey scaffold to publish a changed multi-view proposal, open its normal plan route, load immutable current/proposed SVG and readable pinned source/model/plan/design diffs, and exercise pointer/keyboard semantic selection, relationship hit targets, all changed views, counterpart/absent state, drill/back, styling, zoom/fit and responsive stacking. Through live routes create/reply/resolve/reopen semantic threads; show blocking approval and affected downstream work while unrelated work remains available; then verify exact-tuple approval, old-tab rejection, partial acceptance, retained outdated threads and refresh/reload/restart behavior. Keep deterministic DOM cases supplementary and record concise reproducible evidence.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
