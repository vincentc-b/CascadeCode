---
id: feat_027_002
title: Detect and recover orphaned Task delivery
tier: feature
status: backlog
parent: epic_027
children: []
depends_on:
- feat_027_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-10-31T22:38:17.447745+00:00'
---
# Detect and recover orphaned Task delivery

## Parent Epic

epic_027

## Scope

Extend the direct-report health sweep and a shared supervisor recovery operation. Under the Task lifecycle lock, derive a stable incident, recheck ownership and durable delivery evidence, then requeue a matching validated commit or resume the existing branch, worktree, checkpoint, and pinned execution inputs. Preserve dirty state. Cover restart replay, live-owner protection, bounded cancellation, unsafe or missing Git state, drains before commit or queue, and concurrent requests.

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
