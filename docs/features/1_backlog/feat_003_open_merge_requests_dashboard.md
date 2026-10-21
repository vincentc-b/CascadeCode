---
id: feat_003
title: Open merge requests dashboard
tier: feature
status: backlog
parent: epic_005
children: []
depends_on:
- feat_001
- feat_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
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

## Scope

### Intent

Expose authoritative open merge-request data for War Room consumers without introducing another review-state store.

- Add a read-only query/API over the existing durable review registry.
- Return currently open reviews with stable identifiers, direct review URLs, and feature/epic context.
- Exclude merged and closed reviews according to authoritative registry state.
- Define usable failure behavior for the UI consumer.

### Acceptance criteria

- The API returns open review records and excludes merged or closed records.
- Each record contains the identifiers, display context, state, and direct URL needed by the War Room.
- Repeated reads are side-effect free and lifecycle changes appear from the existing registry.
- Focused integration tests cover filtering, context mapping, and failure behavior.

### Out of scope

- War Room presentation.
- Review mutation or merge actions.
- New review persistence.

## Data structures

Use existing durable review records; define only a read-model DTO.

## API contracts

Read-only list of open reviews with review, feature, and epic identifiers plus direct URL and state.

## Logic flow

Registry query → open-state filter → context mapping → read-only response.

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
