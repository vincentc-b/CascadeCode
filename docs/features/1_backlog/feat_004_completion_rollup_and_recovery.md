---
id: feat_004
title: Completion rollup and recovery
tier: feature
status: backlog
parent: epic_005
children: []
depends_on:
- feat_001
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

## Scope

### Intent

Provide one economical, repeatable sandbox scenario that proves approval, dependency, merge, recovery, and completion behavior together.

- Add a minimal sandbox project or fixture using the repository's existing browser/system harness, preferring Playwright when already supported.
- Demonstrate per-feature approval, blocked dependency dispatch, task/MR completion ordering, restart reconciliation, and epic rollup.
- Keep the scenario deterministic and suitable for local or CI execution.

### Acceptance criteria

- The scenario shows an unapproved or dependency-blocked feature does not dispatch.
- Approval plus completed prerequisites permits dispatch exactly once.
- Completed tasks with an open MR do not complete the feature.
- Merge completes the feature and the final child completes the epic.
- A restart/reconciliation step preserves the same result without duplicate effects.
- Setup and execution are documented in the fixture.

### Out of scope

- Exhaustive lifecycle permutations.
- Production dashboard UI.
- A new test framework when the repository already has a suitable harness.

## Data structures

Use disposable sandbox fixtures only; no production store.

## API contracts

Drive existing public lifecycle entry points and observable status/review endpoints.

## Logic flow

Seed sandbox → approve → verify dependency block → complete prerequisite → dispatch → finish tasks → merge → reconcile → verify rollup.

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
