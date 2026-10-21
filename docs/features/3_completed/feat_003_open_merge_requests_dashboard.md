---
id: feat_003
title: Open review registry API
tier: feature
status: completed
parent: epic_005
children:
- task_007
- task_008
depends_on:
- feat_001
- feat_002
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
# Open review registry API

## Parent Epic

epic_005

## Intent

Expose authoritative open merge-request data for War Room consumers without introducing another review-state store.

## Scope

- Add a read-only API over the durable review registry.
- Return open reviews with stable identifiers, direct URLs, and feature/epic context.
- Exclude merged and closed reviews.

## Acceptance criteria

- Open records are returned and merged/closed records excluded.
- Records contain context, state, and direct URL.
- Reads are side-effect free and covered by focused integration tests.

## Out of scope

War Room presentation, review mutation, and new persistence.

## Data structures

Existing review records plus a read-model DTO.

## API contracts

Read-only open-reviews list.

## Logic flow

Registry query → open filter → context mapping → response.

## Task breakdown
- task_008
- task_007

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_007` (Implement the open-reviews registry API), `task_008` (Add focused integration coverage for open reviews).
