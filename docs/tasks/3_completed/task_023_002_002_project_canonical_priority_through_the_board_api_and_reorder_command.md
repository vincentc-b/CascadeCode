---
id: task_023_002_002
title: Project canonical priority through the board API and reorder command
tier: task
status: completed
parent: feat_023_002
children: []
depends_on:
- task_023_002_001
owners:
- swe
skills: []
parent_rev: 429014ebb3b251f101dbc54c0f974e8c51fb81f2
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Project canonical priority through the board API and reorder command

## Parent Feature

[feat_023_002](../../features/2_active/feat_023_002.md)

## Depends on

- task_023_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Wire the priority service into the War Room's current merged board snapshot and HTTP surface.

Scope:
- Include each backlog epic's canonical feature order and concurrency token in GET /api/board using the same current snapshot that supplies membership.
- Add the guarded reorder mutation using the project's normal process/storage guards.
- On success, return the accepted canonical order and new token; on stale or invalid input, return a clear non-success response and preserve the last confirmed order.
- Ensure the feature lens and any existing backlog/dispatchable queue presentation consume canonical order without re-sorting by feature ID.
- Do not add an extra request or expensive per-poll path, edit feature docs to store order, or alter dispatch eligibility/side effects.

Verification:
- Add API/integration coverage for reload persistence, visibility to a second board client, creation/removal reconciliation, stale concurrent-write refusal, membership validation, and unchanged dispatch/readiness behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
