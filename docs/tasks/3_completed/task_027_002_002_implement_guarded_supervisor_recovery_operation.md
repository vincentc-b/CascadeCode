---
id: task_027_002_002
title: Implement guarded supervisor recovery operation
tier: task
status: completed
parent: feat_027_002
children: []
depends_on:
- task_027_002_001
owners:
- swe
skills: []
parent_rev: 683d03e57ca28762fc779d05cd8078ff484a66be
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Implement guarded supervisor recovery operation

## Parent Feature

[feat_027_002](../../features/2_active/feat_027_002.md)

## Depends on

- task_027_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the shared supervisor recovery operation using the stable incident decision. Recheck ownership and durable delivery evidence while holding the Task lifecycle lock; requeue a matching validated commit or resume the existing branch, worktree, checkpoint, and pinned inputs. Preserve dirty state, bound cancellation, reject unsafe or missing Git state, and drain before commit or queue. Make retries and concurrent requests idempotent.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
