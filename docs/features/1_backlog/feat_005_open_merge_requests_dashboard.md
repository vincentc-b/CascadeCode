---
id: feat_005
title: Open merge requests dashboard
tier: feature
status: backlog
parent: epic_005
children: []
depends_on:
- feat_001
- feat_004
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
# Open merge requests War Room view

## Parent Epic

epic_005

## Scope

### Intent

Give reviewers one direct War Room view of currently open merge requests using the authoritative read-only review API.

- Add an Open MRs view with feature and epic context.
- Link each item directly to its review.
- Reflect merged/closed changes through the API without client-side persistence.
- Provide usable empty, loading, and failure states.
- Extend the sandbox browser flow only enough to demonstrate review discovery and disappearance after merge.

### Acceptance criteria

- Open reviews appear with identifying feature/epic context and working direct links.
- Merged or closed reviews disappear after authoritative state refresh.
- Empty, loading, and failure states are usable.
- The browser scenario proves appearance, navigation target, and disappearance after merge.
- The UI introduces no second review-state store.

### Out of scope

- Review editing or merge actions from War Room.
- General dashboard redesign.
- Exhaustive browser coverage.

## Data structures

Use the API read model as transient UI state only.

## API contracts

Consume the read-only open-review contract from feat_003.

## Logic flow

Load Open MRs → query API → render rows/states → follow direct link or refresh authoritative state.

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
