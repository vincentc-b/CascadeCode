---
id: task_046_002_001
title: Build shared semantic C4 viewer and complete paired navigation
tier: task
status: completed
parent: feat_046_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: f694514be9bfd4a511d970d9539976e576968c57
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Build shared semantic C4 viewer and complete paired navigation

## Parent Feature

[feat_046_002](../../features/2_active/feat_046_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extract the current paired-review SVG interaction into a reusable single-view renderer/navigation primitive for the branch tab. Complete all changed-view selection, explicit absent counterparts, deterministic drill choices and shared back history, element and relationship diff styling with selection, target details, semantic keyboard list/focus, pan/zoom/fit, readable resource links, narrow-screen stacking, and bounded active-page refresh that preserves surviving navigation and drafts. Verify native SVG pointer and keyboard hit targets, view sizing, fit/zoom, and responsive layout in Chromium against running HTTP routes. Expose semantic selection hooks for feat_046_004; do not build its context panel.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
