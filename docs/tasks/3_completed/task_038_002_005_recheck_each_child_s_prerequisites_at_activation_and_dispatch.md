---
id: task_038_002_005
title: Recheck each child's prerequisites at activation and dispatch
tier: task
status: completed
parent: feat_038_002
children: []
depends_on:
- task_038_002_001
- task_038_002_003
owners:
- swe
skills: []
parent_rev: de35487a9e41ccd379ab6b4353a1ae368214fa2b
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Recheck each child's prerequisites at activation and dispatch

## Parent Feature

[feat_038_002](../../features/2_active/feat_038_002.md)

## Depends on

- task_038_002_001
- task_038_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the shared lifecycle result at each child's activation/dispatch dependency check. Re-read that child's current prerequisites immediately before execution authorization, including for children previously bulk approved. Keep existing review and stacked-dispatch restrictions separately enforced and reported. An incomplete or newly unmet/unavailable prerequisite prevents activation or dispatch without relying on approval records.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
