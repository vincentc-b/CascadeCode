---
id: feat_005
title: Open merge requests War Room view
tier: feature
status: completed
parent: epic_005
children:
- task_012
- task_013
depends_on:
- feat_003
- feat_004
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: f82b3c99c3508cb6791e5680d65d574e199ddd89
created: '2026-10-21'
updated: '2026-10-21'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Open merge requests War Room view

## Parent Epic

epic_005

## Intent

Give reviewers one direct War Room view of open merge requests using the authoritative API.

## Scope

- Show feature/epic context and direct review links.
- Reflect authoritative merged/closed changes.
- Provide empty, loading, and failure states.
- Extend the sandbox flow for appearance and disappearance.

## Acceptance criteria

- Open reviews appear with working links.
- Merged/closed reviews disappear after refresh.
- UI states are usable and no second store is introduced.
- Browser flow proves the critical path.

## Out of scope

Review mutation, broad dashboard redesign, and exhaustive browser coverage.

## Data structures

Transient API read model only.

## API contracts

Consume feat_003 open-reviews endpoint.

## Logic flow

Load → query → render → link or refresh.

## Task breakdown
- task_013
- task_012

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_012` (Implement the open merge requests War Room view), `task_013` (Prove the open-review lifecycle in the sandbox browser flow).
