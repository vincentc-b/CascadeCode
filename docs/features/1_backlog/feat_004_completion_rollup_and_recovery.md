---
id: feat_004
title: Lifecycle sandbox demonstration
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
# Lifecycle sandbox demonstration

## Parent Epic

epic_005

## Intent

Provide one economical, repeatable scenario proving approval, dependency, merge, recovery, and completion behavior.

## Scope

- Use the existing browser/system harness, preferring Playwright when supported.
- Demonstrate approval, dependency gating, task/MR ordering, restart recovery, and rollup.

## Acceptance criteria

- Blocked work does not dispatch; ready work dispatches once.
- Open MR prevents completion; merge enables feature and epic rollup.
- Restart reconciliation is idempotent.
- Setup and execution are documented.

## Out of scope

Exhaustive permutations, dashboard UI, and a new test framework.

## Data structures

Disposable fixtures only.

## API contracts

Drive existing public lifecycle entry points.

## Logic flow

Seed → approve → gate → complete dependency → dispatch → tasks → merge → reconcile → verify.

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
