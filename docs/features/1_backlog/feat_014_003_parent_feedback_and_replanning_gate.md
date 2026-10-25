---
id: feat_014_003
title: Parent feedback and replanning gate
tier: feature
status: backlog
parent: epic_014
children: []
depends_on:
- feat_014_001
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

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
