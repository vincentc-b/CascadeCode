---
id: task_035_003_002
title: Integrate restart-safe recovery into the admitted rebase workflow
tier: task
status: completed
parent: feat_035_003
children: []
depends_on:
- task_035_003_001
owners:
- swe
skills: []
parent_rev: de399fe429b89cf9bf3c8061b0ddfbccfad896e0
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Integrate restart-safe recovery into the admitted rebase workflow

## Parent Feature

[feat_035_003](../../features/2_active/feat_035_003.md)

## Depends on

- task_035_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope

Wire the recovery reconciler into the admitted conflict-resolution/rebase execution path and make externally visible workflow effects idempotent.

## Required outcomes

- Interrupted and retried actions resume or reconcile safely from durable state.
- Commits, pushes, reviews, War Room completion messages, and lifecycle completion events occur at most once per action identity.
- Semantic conflicts become structured blockers with preserved checkpoint evidence and actionable resume instructions.
- Clean rebases and already-completed actions report the correct final result.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
