---
id: feat_026_001
title: Durable action recovery state
tier: feature
status: backlog
parent: epic_026
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Durable action recovery state

## Parent Epic

epic_026

## Scope

## Objective

Persist one recoverable lifecycle action across retries and supervisor restarts.

## Scope

- Stable action identity and recovery state.
- Failure classification: deterministic repair, transient retry, owner decision, human gate, terminal blocker.
- Serialized execution, bounded attempts, idempotent resume, and attempt history.

## Acceptance

Restart and concurrent-retry integration tests prove one logical action creates no duplicate team turns, reviews, merges, or completion events.

## Out of scope

Recovery implementations, War Room presentation, and generic workflow orchestration.

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
