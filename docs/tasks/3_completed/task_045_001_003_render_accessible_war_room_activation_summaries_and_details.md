---
id: task_045_001_003
title: Render accessible War Room activation summaries and details
tier: task
status: completed
parent: feat_045_001
children: []
depends_on:
- task_045_001_002
owners:
- swe
skills: []
parent_rev: d4c70116ed7d3fa02a4ff6e610a2ba41214156cc
created: '2026-11-12'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Render accessible War Room activation summaries and details

## Parent Feature

[feat_045_001](../../features/2_active/feat_045_001.md)

## Depends on

- task_045_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Render the backend-provided readiness.explanation in War Room feature rows: one compact summary, deterministic primary reason, expandable additional reasons and satisfied prerequisites, existing action/review links, clear missing-evidence text, and historical attempt context. Use semantic controls, keyboard access, readable contrast, and screen-reader labels; do not encode eligibility in JavaScript. Add browser journey for approved feature waiting on active sibling, then readiness refresh after sibling completion without extra approval, plus expansion/links/keyboard/text assertions. Keep creation/acknowledgement storage out of scope.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
