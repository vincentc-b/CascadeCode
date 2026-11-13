---
id: task_046_001_005
title: Prove normal planning-to-browser architecture review and restart recovery
tier: task
status: completed
parent: feat_046_001
children: []
depends_on:
- task_046_001_004
owners:
- swe
skills: []
parent_rev: e764058ea543f073d9075970e610792a3063b4c8
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove normal planning-to-browser architecture review and restart recovery

## Parent Feature

[feat_046_001](../../features/2_active/feat_046_001.md)

## Depends on

- task_046_001_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build the primary fresh-project journey using registered planning/publication tools, actual Structurizr renderer, production War Room HTTP, and Playwright Chromium. Open the normally created feature from its /plan URL and confirm real current/proposed SVG, exact revisions, semantic inventory/navigation/diff metadata and readable links; include first-model empty baseline, no-change and failure states where focused API coverage is cheaper. Restart server and verify pending/ready work recovers and repeated requests reuse bounded work. Add focused crash/retry and stale-write race tests. Retain exact targeted publication/HTTP/cache/real-renderer/browser test commands and measured payload limits in the feature artifact; do not seed review JSON or fabricate paired payloads for the primary journey.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
