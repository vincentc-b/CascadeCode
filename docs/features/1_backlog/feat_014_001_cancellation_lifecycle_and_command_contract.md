---
id: feat_014_001
title: Cancellation lifecycle and command contract
tier: feature
status: backlog
parent: epic_014
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Cancellation lifecycle and command contract

## Parent Epic

epic_014

## Scope

Define and implement the canonical cancelled lifecycle state and a single cancellation entry point for epics, features, and tasks. Require a non-empty reason, reject completed work, make repeated cancellation idempotent, and persist cancellation metadata before downstream effects. Acceptance must cover backlog and active items plus explicit invalid transitions.

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
