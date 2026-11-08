---
id: task_037_002_005
title: Verify end-to-end gate consistency and structured recovery
tier: task
status: completed
parent: feat_037_002
children: []
depends_on:
- task_037_002_002
- task_037_002_003
- task_037_002_004
owners:
- swe
skills: []
parent_rev: 2e851f651db32f7ec9b7c1271242a2a803da4d39
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify end-to-end gate consistency and structured recovery

## Parent Feature

[feat_037_002](../../features/2_active/feat_037_002.md)

## Depends on

- task_037_002_002
- task_037_002_003
- task_037_002_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use existing dispatch, execution, and approval integration fixtures to verify the combined behavior: future Feature/SWE failures block Epic activation before side effects; late child overrides cannot gain approval; legacy resolution errors fail closed; manual and automatic paths agree; drift blocks each provider launch tier; and a later dispatch failure keeps an accepted approval while exposing all role diagnostics. Confirm one blocker survives restart and clears only after fresh whole-scope success. Use fake inventory/process boundaries, no live provider turns. Fix only integration gaps found by these checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
