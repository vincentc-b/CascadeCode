---
id: feat_035_002
title: Execute and publish an owned review rebase
tier: feature
status: backlog
parent: epic_035
children: []
depends_on:
- feat_035_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Execute and publish an owned review rebase

## Parent Epic

epic_035

## Scope

## Objective

Run an admitted resolution action in a dedicated repository-backed team turn and safely update the same open review source branch.

## Required outcomes

- The turn receives only the authorized review/worktree, linked Git metadata, minimal edit/test operations, and push credentials.
- It records worktree state and source/target remote SHAs, fetches, and revalidates authorization and heads before mutation.
- It rebases the owned source onto the target, permits edits only to conflicted/owned paths, and blocks unresolved semantic ambiguity.
- It runs repository-defined relevant checks and captures results.
- It re-reads the remote source and pushes only with an explicit `--force-with-lease=<source-ref>:<observed-sha>`.
- Lease races, failed tests, dirty unrelated paths, or changed authorization stop without discarding user work.
- An end-to-end fixture exercises one semantic conflict and one clean rebase.

## Non-goals

No target/trunk rewrite, new review creation, review replacement, unrestricted shell, automatic product decisions, or bypass of existing lifecycle/review gates.

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
