---
id: feat_027_003
title: Expose scoped Task recovery and recovery state
tier: feature
status: completed
parent: epic_027
children:
- task_027_003_001
- task_027_003_002
- task_027_003_003
depends_on:
- feat_027_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 5eae65d4cbe2e5eeb92bb5800cc851ff16802e20
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-10-31T22:38:20.070943+00:00'
---
# Expose scoped Task recovery and recovery state

## Parent Epic

epic_027

## Scope

Add Feature Team recover_task(task_id) for direct children using the shared supervisor recovery operation. Return precise outcomes and surface incidents through existing parent blockage provenance and War Room state, including semantic merge conflicts; clear only the matching derived blocker. Cover scope authorization, simultaneous tool/sweep requests, outcome rendering, and blocker lifecycle.

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
- task_027_003_003
- task_027_003_002
- task_027_003_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_027_003_001` (Implement scoped Feature Team recover_task command), `task_027_003_002` (Project Task recovery incidents and blocker lifecycle), `task_027_003_003` (Add end-to-end coverage for scoped recovery behavior).
