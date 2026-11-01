---
id: feat_030_002
title: Durable idempotent active-to-backlog transition
tier: feature
status: backlog
parent: epic_030
children: []
depends_on:
- feat_030_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Durable idempotent active-to-backlog transition

## Parent Epic

epic_030

## Scope

Deliver turn quiescence, per-Epic lifecycle locking and locked eligibility recheck, a durable replay-safe transition journal, active-run artifact preservation, source-brief restoration, active-pointer removal, stale-run invalidation, recovery, and deduplicated audit emission. Verify concurrent/repeated requests, restart at each durable boundary, racing turns, Git safety refusals, and no operator-trunk mutation.

## Data structures

TBD.

## API contracts

TBD.

## Logic flow

```mermaid
flowchart TD
  A[Start] --> B[End]
```

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
