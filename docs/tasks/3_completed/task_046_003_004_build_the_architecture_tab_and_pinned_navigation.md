---
id: task_046_003_004
title: Build the Architecture tab and pinned navigation
tier: task
status: completed
parent: feat_046_003
children: []
depends_on:
- task_046_003_003
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
# Build the Architecture tab and pinned navigation

## Parent Feature

[feat_046_003](../../features/2_active/feat_046_003.md)

## Depends on

- task_046_003_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add accessible top-level Architecture tab while preserving board/operational panels and selected-tab navigation state. Select known contexts; default to the session target; show repository, branch or detached HEAD, full code/document revisions, dirty status, association provenance and accepted lineage separately. Consume the shared single-view C4 viewer for initial/view/level selection, semantic element and relationship details, deterministic drill choices/back, keyboard selection, pan/zoom/fit and source links. Show pending/error/missing-model states without stalling the board. Check HEAD only while active, display an update indicator and switch all content on explicit snapshot refresh; ignore late responses from older selections. Encode context, snapshot ID, view/level and semantic target in reloadable deep links and explain invalid links. Expose selection/context events for feat_046_004 and link to plan review only for a proven associated proposal.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
