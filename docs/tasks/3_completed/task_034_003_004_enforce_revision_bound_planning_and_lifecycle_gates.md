---
id: task_034_003_004
title: Enforce revision-bound planning and lifecycle gates
tier: task
status: completed
parent: feat_034_003
children: []
depends_on:
- task_034_003_003
owners:
- swe
skills: []
parent_rev: 37a365b227ed51c9ab6f3e7792e5e547dfc6d8e0
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce revision-bound planning and lifecycle gates

## Parent Feature

[feat_034_003](../../features/2_active/feat_034_003.md)

## Depends on

- task_034_003_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Wire review-unit freshness, required model validity, scoped blocking threads, and affected-work holds into approval, task dispatch, integration, feature merge, and closeout safe boundaries. Enable gates explicitly with versioned rollout state: already executing work keeps recorded policy; new or materially revised proposals bind reviewed artifacts. No rollout exception permits a claimed diagram change with a missing model. Preserve existing human approval boundaries and report actionable refusal reasons.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
