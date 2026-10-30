---
id: feat_022_002
title: Unresolved blockage propagation and reconciliation
tier: feature
status: completed
parent: epic_022
children:
- task_022_002_001
- task_022_002_002
- task_022_002_003
depends_on:
- feat_022_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 3e0892028c607152d32d46d4af0c734a19e4b553
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
approved_at: '2026-10-25T03:11:47.058534+00:00'
---
# Unresolved blockage propagation and reconciliation

## Parent Epic

epic_022

## Scope

## Objective

Propagate an unresolved direct-report blockage into the supervisor’s canonical blocked/stuck state, then safely remove only that monitoring-derived cause after recovery.

## Required outcomes

- Persist machine-readable provenance containing the originating direct-report ID and concise reason.
- Reuse canonical state transitions and optimistic/version checks; never write status storage directly.
- Apply the same direct-report rule at feature and epic levels so task blockage can propagate through the hierarchy.
- Treat already-applied concurrent transitions as success and never mutate or resurrect terminal work.
- On later sweeps, reconcile only monitoring-derived causes whose child condition has cleared; preserve unrelated manual and sibling blockers.

## Acceptance coverage

Integration tests demonstrate unresolved child propagation, task → feature → epic visibility, concurrent/manual-state safety, recovery clearing, and preservation of unrelated blocker causes.

## Non-goals

No new incident subsystem, dashboard, paging integration, recursive hierarchy scan, or automated resolution of decisions requiring human authority.

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
- task_022_002_003
- task_022_002_002
- task_022_002_001

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_022_002_001` (Implement provenance-aware direct-report blockage propagation), `task_022_002_002` (Reconcile monitoring-derived blockers across feature and epic sweeps), `task_022_002_003` (Add lifecycle integration coverage for blockage propagation and recovery).
