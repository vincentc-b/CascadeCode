---
id: task_051_002_001
title: Admit scoped open review repairs in the existing Feature action ledger
tier: task
status: completed
parent: feat_051_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 63fa25b6654ed428498170a9bcbf7358227f7cbb
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Admit scoped open review repairs in the existing Feature action ledger

## Parent Feature

[feat_051_002](../../features/2_active/feat_051_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the open Feature review request and admission contract in cascade/feature/repair.py. Persist stable request ID and content digest, reason/evidence, parent or authenticated human authority, accountable Feature, original review identity/forge/source-target route, observed heads and generation, approval/scope, existing claim and budget identity before queueing. Under lifecycle and mutation-owner fences recheck current review, status, approval, scope, governing comments, dependencies, cancellation, heads, lease and budget. Admit without a Task mismatch; preserve the completed-open legacy reconciliation. Same-ID changed content, stale evidence and missing prerequisites return typed refusals; concurrent requests join or defer to one writer. Preserve action identity and crash replay at prepared/authority/active introduction boundaries. Update cascade/feature/DESIGN.md and affected Feature/Watchdog native Code nodes/contracts, and test with temporary Git repositories plus fault injection and concurrency.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
