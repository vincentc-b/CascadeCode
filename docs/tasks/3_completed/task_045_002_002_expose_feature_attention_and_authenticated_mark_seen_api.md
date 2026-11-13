---
id: task_045_002_002
title: Expose feature attention and authenticated Mark seen API
tier: task
status: completed
parent: feat_045_002
children: []
depends_on:
- task_045_002_001
owners:
- swe
skills: []
parent_rev: b9afd02b8b6040b5f2232a088a63ccc058666fdb
created: '2026-11-13'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose feature attention and authenticated Mark seen API

## Parent Feature

[feat_045_002](../../features/2_active/feat_045_002.md)

## Depends on

- task_045_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Project ledger attention into GET /api/board using the current board snapshot and expose one request-scoped human-authenticated POST /api/feature_attention/mark_seen. Validate feature IDs and input, make acknowledgement idempotent and durable, report storage errors, and return monotonic revision plus current feature state. Pending counts exclude terminal children and require active non-cancelling parents. Keep activation summary/actions from feat_045_001 authoritative and independent. Build one focused API/state integration matrix spanning bootstrap, corrective minting, auth, repeat writes, concurrent responses, replay, restart, revisions, cancellation/completion, split roots and unchanged product repository/approvals/status/blockers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
