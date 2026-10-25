---
id: feat_014_003
title: Parent feedback and replanning gate
tier: feature
status: completed
parent: epic_014
children:
- task_014_003_001
- task_014_003_002
- task_014_003_003
depends_on:
- feat_014_001
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
approved_at: '2026-10-25T01:22:54.689268+00:00'
---
# Parent feedback and replanning gate

## Parent Epic

epic_014

## Scope

When a feature or task is cancelled, emit durable structured feedback to its parent and pause/gate the parent before further dispatch until the user chooses a disposition. Support continue with reduced scope, replace/replan, or cancel parent; record the choice in the owning plan/decision trail. Epic cancellation has no parent escalation. Verify the end-to-end user workflow.

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
- task_014_003_003
- task_014_003_002
- task_014_003_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_014_003_001` (Define parent cancellation feedback and gate contract), `task_014_003_002` (Gate parent dispatch and apply user disposition), `task_014_003_003` (Verify end-to-end cancellation replanning workflow).
