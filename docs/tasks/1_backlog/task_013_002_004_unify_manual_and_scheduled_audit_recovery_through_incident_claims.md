---
id: task_013_002_004
title: Unify manual and scheduled audit recovery through incident claims
tier: task
status: backlog
parent: feat_013_002
children: []
depends_on:
- task_013_002_003
owners:
- swe
skills: []
parent_rev: 20b90d6adbec9b20361ed4751aa1e8339cc8fa77
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Unify manual and scheduled audit recovery through incident claims

## Parent Feature

[feat_013_002](../../features/2_active/feat_013_002.md)

## Depends on

- task_013_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Expose an explicit guarded manual audit request even when scheduled audits are disabled. Coalesce manual requests with an in-flight audit without moving the periodic deadline. Route scheduled, manual, and concurrent-parent recovery through the existing incident claims and fresh lifecycle preconditions; avoid duplicate repair execution. Hand off durable actions to supervised workers rather than doing repair under scheduler/global locks. Add checks for duplicate/manual requests and cross-process claim behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
