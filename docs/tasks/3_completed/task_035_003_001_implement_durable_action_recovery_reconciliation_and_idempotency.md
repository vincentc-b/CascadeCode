---
id: task_035_003_001
title: Implement durable action recovery reconciliation and idempotency
tier: task
status: completed
parent: feat_035_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 0bdeb078012ec1fe2bc40cee098cde238624dc59
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Implement durable action recovery reconciliation and idempotency

## Parent Feature

[feat_035_003](../../features/2_active/feat_035_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope

Define and implement the durable per-action recovery/checkpoint model and reconciliation logic that compares persisted action state, local rebase/worktree state, and the current remote head.

## Required outcomes

- A stable action identity drives restart behavior and side-effect deduplication.
- Reconciliation selects exactly one outcome: resume, safe retry, already-completed reconciliation, or blocker.
- Checkpoints retain refs/SHAs, affected paths, command/test summaries, and resume instructions needed by downstream workflow handling.
- Focused tests cover state transitions and remote-head changes without redundant broad unit coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
