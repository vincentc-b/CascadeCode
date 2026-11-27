---
id: feat_029_002
title: Atomic active-item provider recovery
tier: feature
status: completed
parent: epic_029
children:
- task_029_002_001
- task_029_002_002
- task_029_002_003
depends_on:
- feat_029_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 26ffbfe93ba528417b7bf86bd7ff76e3e7277d84
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-11-02T04:46:23.558910+00:00'
---
# Atomic active-item provider recovery

## Parent Epic

epic_029

## Scope

Implement one human-authorized recovery command across Epic, Feature, and Task. Serialize with lifecycle activity, validate every affected role plus reasoning/tier/flex selection, preserve plan/progress/worktree/dirty files, atomically reconcile persisted selection and checkpoint pins, and either resume proven-compatible state or reconstruct a fresh role turn. Keep child selections unchanged and make retry idempotent.

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
- task_029_002_003
- task_029_002_002
- task_029_002_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_029_002_001` (Implement atomic active-item provider recovery engine), `task_029_002_002` (Wire human-authorized recovery command into lifecycle serialization), `task_029_002_003` (Verify cross-tier recovery preservation and retry behavior).
