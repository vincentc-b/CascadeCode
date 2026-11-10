---
id: feat_044_001
title: Persist fair background audit reassessment and truthful incident projections
tier: feature
status: backlog
parent: epic_044
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Persist fair background audit reassessment and truthful incident projections

## Parent Epic

epic_044

## Scope

Own epic success criteria 1, 3, 4, 8, 9 and producer-side regressions in 10–11. Define/version the shared current/coverage/history projection and source/generation identity contract before consumer implementation. Extend the existing supervisor audit lane with durable pending coverage, fair rotation between ongoing and historical unresolved work, bounded per-item isolation, pass evidence reuse and restart-safe coalescing. Publish atomic bounded snapshots/history indexes; retain source ledgers unchanged. Record occurrence, observation and freshness separately; unknown/deleted/rerouted work must stay explicit. Legacy identity may be reconstructed only from unambiguous durable evidence with provenance; otherwise classify as historical/unverifiable. Keep fresh authoritative checks at every repair/admission boundary and existing owner investigation delivery/cooldown semantics. Verify slow-first-item plus later current blocker, repeated generations, completed publication obligations, restart and obsolete-generation repair rejection. Establish producer budgets and schema fixtures for subsequent features. No new dependencies or recovery-policy changes.

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
