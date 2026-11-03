---
id: feat_031_002
title: War Room recovery status and operator guidance
tier: feature
status: backlog
parent: epic_031
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
flex_mode: false
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-11-03T20:14:23.521079+00:00'
---
# War Room recovery status and operator guidance

## Parent Epic

epic_031

## Scope

## Outcome

Expose one durable, actionable incident state on the affected War Room row from first failure through resolution or human blocker.

## Scope

- Project recovery state through the existing API and board model.
- Show failure-specific copy, owner, safe reason, affected branch or paths, last attempt, and action/review link.
- Only claim agents are investigating after the team request is durably queued.
- Suppress duplicate warnings and repeated toasts.

## Acceptance focus

Refreshes and restarts preserve status; transitions are exact; blocked incidents name the owner and next step; resolution clears the active warning.

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
