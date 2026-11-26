---
id: task_046_005_002
title: Prove real branch architecture browsing and context recovery
tier: task
status: completed
parent: feat_046_005
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: fb54583c9195f09e417771bb95a326c7c6e27932
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove real branch architecture browsing and context recovery

## Parent Feature

[feat_046_005](../../features/2_active/feat_046_005.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Own acceptance B1–B5 in real War Room with pinned local Structurizr and native Chromium. Start from the actual default branch and pinned commit; exercise browsing, a second differing branch, deep-link restoration, HEAD update and explicit refresh, detached/dirty/missing states, distinct split code/doc refs, and absent-association handling. Use real context and snapshot routes and a fixture whose source revisions are recorded. Repair epic-critical integration defects and capture exact commands, refs, pass/fail, and screenshots or recording for final evidence. Keep this browser proof independent of helper-only or mock routes.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
