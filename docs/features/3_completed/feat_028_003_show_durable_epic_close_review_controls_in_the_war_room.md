---
id: feat_028_003
title: Show durable epic close-review controls in the War Room
tier: feature
status: completed
parent: epic_028
children:
- task_028_003_001
- task_028_003_002
depends_on:
- feat_028_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 034232f417503080ae33f6a2c9cdbddf49ab2ed9
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-11-03T01:17:25.327918+00:00'
---
# Show durable epic close-review controls in the War Room

## Parent Epic

epic_028

## Scope

Render the persisted epic close stage beside the Epic row's Close action. Show a safe external `Open implementation review` link while pending, retain it across refresh/navigation/restart, expose `Finish close` when automatic reconciliation cannot run, and replace ambiguous status with actionable blockers. Reuse the existing safe external-link component and avoid rendering forge text as HTML. Add browser coverage for link accessibility, refresh, pending and blocker states, and completion.

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
- task_028_003_002
- task_028_003_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_028_003_001` (Render durable epic close-review state and controls in the War Room), `task_028_003_002` (Cover epic close-review controls with browser tests).
