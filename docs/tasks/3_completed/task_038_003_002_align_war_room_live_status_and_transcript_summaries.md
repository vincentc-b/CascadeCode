---
id: task_038_003_002
title: Align War Room live status and transcript summaries
tier: task
status: completed
parent: feat_038_003
children: []
depends_on:
- task_038_003_001
owners:
- swe
skills: []
parent_rev: dc7bd73f904777a080fed384a7197c74839daac9
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Align War Room live status and transcript summaries

## Parent Feature

[feat_038_003](../../features/2_active/feat_038_003.md)

## Depends on

- task_038_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Consume the same structured dependency projection in War Room live status and generated current transcript summaries. Keep historical transcript messages verbatim and dated; label their observed-at status separately from current status. Do not treat legacy chat without evidence as a live assertion or parse agent prose/document-access errors for dependency state. Use the normal board/readiness refresh so a completed dependency clears on the next live refresh without rewriting old chat. Preserve existing scoped authorization and review/stacked behavior. Add one UI-level assertion for current-versus-historical labeling.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
