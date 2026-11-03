---
id: feat_028_001
title: Prepare and reconcile epic closure through one implementation review
tier: feature
status: backlog
parent: epic_028
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-11-03T01:17:17.802516+00:00'
---
# Prepare and reconcile epic closure through one implementation review

## Parent Epic

epic_028

## Scope

Implement the single-review epic lifecycle: stage the epic plan's completed-state move on the implementation branch before opening the review; keep closure pending while it is open; after merge, verify both the merged review and completed epic document on remote trunk; finalize without creating a terminal-only closeout PR. Preserve the human review policy and leave the operator product-trunk checkout untouched. Add high-signal coverage for idempotent preparation, verification blockers, reconciliation, and absence of a second PR.

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
