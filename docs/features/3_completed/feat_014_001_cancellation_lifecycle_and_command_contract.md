---
id: feat_014_001
title: Cancellation lifecycle and command contract
tier: feature
status: completed
parent: epic_014
children:
- task_014_001_001
- task_014_001_002
- task_014_001_003
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 3fb1f723ae44fdd5da04bfc1159ee6e0c3da02b8
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-10-25T01:22:51.811212+00:00'
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
- task_014_001_003
- task_014_001_002
- task_014_001_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_014_001_001` (Add canonical cancelled state and cancellation metadata), `task_014_001_002` (Implement the unified cancellation command contract), `task_014_001_003` (Cover cancellation lifecycle and ordering with acceptance tests).
