---
id: task_027_002_004
title: Verify orphan-delivery recovery lifecycle
tier: task
status: completed
parent: feat_027_002
children: []
depends_on:
- task_027_002_003
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
# Verify orphan-delivery recovery lifecycle

## Parent Feature

[feat_027_002](../../features/2_active/feat_027_002.md)

## Depends on

- task_027_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration coverage for validated-commit requeue, execution resume with preserved dirty state and pinned inputs, restart replay, live-owner protection, bounded cancellation, unsafe or missing Git state, drains before commit/queue, and concurrent recovery requests. Prefer lifecycle-level coverage over redundant low-level mocks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
