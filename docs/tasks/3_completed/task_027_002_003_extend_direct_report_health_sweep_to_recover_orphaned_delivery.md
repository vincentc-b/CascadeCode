---
id: task_027_002_003
title: Extend direct-report health sweep to recover orphaned delivery
tier: task
status: completed
parent: feat_027_002
children: []
depends_on:
- task_027_002_002
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
# Extend direct-report health sweep to recover orphaned delivery

## Parent Feature

[feat_027_002](../../features/2_active/feat_027_002.md)

## Depends on

- task_027_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend the direct-report health sweep to identify eligible orphaned Task delivery and invoke the shared supervisor recovery operation. Protect live owners, avoid duplicate recovery, and ensure restart replay converges through the same guarded path without bypassing lifecycle locking or delivery validation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
