---
id: task_039_002_004
title: Resume blocked dependency checks with deduplication and partial-state recovery
tier: task
status: completed
parent: feat_039_002
children: []
depends_on:
- task_039_002_003
owners:
- swe
skills: []
parent_rev: 39f063274050f79b24323accc683537a7fe35c67
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resume blocked dependency checks with deduplication and partial-state recovery

## Parent Feature

[feat_039_002](../../features/2_active/feat_039_002.md)

## Depends on

- task_039_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Route human ping/resume through existing run/checkpoint and provider recovery. Treat ping only as a request to revalidate; recheck every blocked entry and any passed entry affected by manifest/environment change. Under lifecycle serialization deduplicate repeated/concurrent requests, admit stable attempt IDs, prevent concurrent installs for the same scope/environment, and bound retries/timeouts. After interruption inspect actual installed state before retrying; retain append-only attempts, accepted work, and planning history. Recheck current approval, scope, policy, and evidence at each mutation and completion boundary. Persist blocker guidance when still unresolved and resume existing planning only when readiness and feasibility are current. Integration tests cover human install/recheck, duplicate ping, restart/partial setup, stale queued approval/result, and no-dependency path.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
