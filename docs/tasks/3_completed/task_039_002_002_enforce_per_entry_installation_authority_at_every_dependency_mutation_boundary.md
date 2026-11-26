---
id: task_039_002_002
title: Enforce per-entry installation authority at every dependency mutation boundary
tier: task
status: completed
parent: feat_039_002
children: []
depends_on:
- task_039_002_001
owners:
- swe
skills: []
parent_rev: a8428762c67d69f3f73e99a1cfe08c813f388d5b
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce per-entry installation authority at every dependency mutation boundary

## Parent Feature

[feat_039_002](../../features/2_active/feat_039_002.md)

## Depends on

- task_039_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Consume slice A independent approval records and guard. Classify install, upgrade, and implicit pull operations as mutations; read-only discovery/validation stays available. Enforce exact binding and current execution policy under lifecycle admission and immediately before provider dispatch, including bootstrap, MCP/UI entry routes, and retry/resume; recheck authority and revision when accepting completion. Fail closed for absent or stale approval, unknown exact version/source/digest, changed ID/version/source/integrity/environment/scope/destination/operation/cleanup, denied system mutation, prompts for credentials/license, and unauthorized sudo/default changes. Preserve unaffected approvals. Add integration/API tests proving denial before mutation under yolo, owned-worktree access, and approved plans; independently approved operation succeeds, while ping/sign-off never grants installation authority.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
