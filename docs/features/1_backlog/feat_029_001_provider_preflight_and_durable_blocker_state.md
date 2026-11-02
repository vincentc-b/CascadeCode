---
id: feat_029_001
title: Provider preflight and durable blocker state
tier: feature
status: backlog
parent: epic_029
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Provider preflight and durable blocker state

## Parent Epic

epic_029

## Scope

Add the shared provider/model/tier capability check at Epic activation and Feature/Task dispatch, recheck at the execution boundary, classify deterministic versus transient setup failures, and persist one safe restart-visible provider-blocked incident per work item. Do not create worktrees/checkpoints on failed preflight or affect unrelated work.

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
