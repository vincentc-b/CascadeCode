---
id: task_045_001_002
title: Serialize bounded board explanations and actual dispatch evidence
tier: task
status: completed
parent: feat_045_001
children: []
depends_on:
- task_045_001_001
owners:
- swe
skills: []
parent_rev: d4c70116ed7d3fa02a4ff6e610a2ba41214156cc
created: '2026-11-12'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Serialize bounded board explanations and actual dispatch evidence

## Parent Feature

[feat_045_001](../../features/2_active/feat_045_001.md)

## Depends on

- task_045_001_001

## Acceptance criteria

- Implement the pinned version 1 schema and code-to-source table in the current feature plan, including `source_ids`, `evaluated_at`, six source states/revisions, and actual attempt identity/history state. Preserve `approved` and `blockers` and action-boundary refusal codes.
- Cover `backlog` and `ready_to_plan` open features. Reuse one request-scoped board, dependency, review/thread and bounded provider snapshot; obtain missing or stale evidence as unknown without poll writes or new per-feature Git/provider work.
- Revision-bind actual approval and dispatch-base evidence. Treat older unverified approval timestamps or stored selections as unknown until validated; allow cheap complete Epic-base evidence and nonpoll refresh paths to yield ready awaiting dispatch.
- Persist actual refusal/start outcomes only at real dispatch boundaries using tracking root resolution, cross-process locking, atomic replacement and monotonic attempt ordering. A later poll timestamp alone never marks an attempt historical.
- Establish legitimate dependency-satisfied approval in the three existing War Room fixtures. Cover approved 034_008 waiting for executing 034_009, completion transition without reapproval, simultaneous blockers, execution versus review, unknown evidence, actual refusal, serial/stacked parity and polling cost.

## Files likely touched

`cascade/war_room/serialize.py`, `cascade/feature/readiness.py`, `cascade/approvals.py`, `cascade/stacked_dispatch.py`, the actual dispatch boundary and focused `tests/war_room/` or feature readiness integration tests.

## Implementation notes

Wire version 1 readiness.explanation into GET /api/board using one request-scoped board/dependency/review snapshot and existing cached provider inventory. Supply evaluated_at, per-source freshness/revision, existing valid action links, affected IDs, and last actual dispatch outcome. Persist only actual dispatch refusal/start with safe reason and source identity under tracking-owned workspace; never write from polling. Preserve legacy fields and actual gate rechecks. Repair test_board_feature_readiness approval fixtures via legitimate dependency-satisfied state. Add focused API/integration tests for simultaneous blockers, changed plan, stale/missing evidence, empty blockers, real refusal, and no dispatch/provider discovery/costly preflight during render/poll.

## Skills

_(none)_

## Test plan

Run focused Python API/integration tests for the new contract, existing dispatch refusal tests, and the corrected board readiness fixtures. Keep validation bounded.

## Out of scope

Browser presentation, new-work attention/Mark seen, scheduler changes, and architecture publication repair.
