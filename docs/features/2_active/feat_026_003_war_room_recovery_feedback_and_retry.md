---
id: feat_026_003
title: War Room recovery feedback and retry
tier: feature
status: active
parent: epic_026
children:
- task_026_003_001
- task_026_003_002
- task_026_003_003
depends_on:
- feat_026_001
- feat_026_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 62a760aea00df46cc98915c547ae6f1c12c91d19
created: '2026-10-26'
updated: '2026-10-27'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-10-26T05:46:58.310972+00:00'
---
# War Room recovery feedback and retry

## Parent Epic

epic_026

## Scope

## Objective

Expose recovery progress and one safe retry path on the original War Room action.

## Scope

- Show recovery phase, typed reason, attempt count, owner, affected checkout or branch, and next safe step.
- Provide one retry control for retryable terminal blockers.
- Keep human approval and review gates distinct from retry.

## Acceptance

Transient forge failure, permission refusal, and concurrent retry scenarios show the correct state and produce at most one resumed execution.

## Out of scope

A second orchestration path or bypasses for approval, review, credentials, or permissions.

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
- task_026_003_003
- task_026_003_002
- task_026_003_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_026_003_001` (Implement recovery status and atomic retry backend), `task_026_003_002` (Show recovery feedback and safe retry in War Room), `task_026_003_003` (Verify recovery feedback and retry scenarios).
