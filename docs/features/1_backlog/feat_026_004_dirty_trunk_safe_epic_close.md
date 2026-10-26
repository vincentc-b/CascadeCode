---
id: feat_026_004
title: Dirty-trunk-safe epic close
tier: feature
status: backlog
parent: epic_026
children: []
depends_on:
- feat_026_001
- feat_026_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Dirty-trunk-safe epic close

## Parent Epic

epic_026

## Scope

## Objective

Complete epic close without touching unrelated changes in the operator's product trunk checkout.

## Scope

- Use an isolated checkout based on verified remote product trunk for trunk-dependent closeout work.
- Reuse or open the normal closeout review.
- Verify the implementation review is merged and terminal closeout review is satisfied.
- Resume the original persisted close action.

## Acceptance

An epic closes while operator trunk contains unrelated tracked and untracked files; those files and the operator checkout remain byte-for-byte and index-state unchanged.

## Out of scope

Stashing, cleaning, resetting, committing, or merging operator changes.

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
