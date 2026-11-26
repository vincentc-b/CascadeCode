---
id: task_013_001_006
title: Verify all-tier audit foundations through integration fixtures
tier: task
status: completed
parent: feat_013_001
children: []
depends_on:
- task_013_001_002
- task_013_001_003
- task_013_001_004
- task_013_001_005
owners:
- swe
skills: []
parent_rev: e42512edf87a275dc4c15513cf66b40350b9ad28
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify all-tier audit foundations through integration fixtures

## Parent Feature

[feat_013_001](../../features/2_active/feat_013_001.md)

## Depends on

- task_013_001_002
- task_013_001_003
- task_013_001_004
- task_013_001_005

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Prove the feature's shared observation, candidate, incident, authority, and reservation contracts through focused integration fixtures. Document the stable API surface for the scheduling and repair features.

## Acceptance
- Task observations include lease/heartbeat, phase, checkpoint, pinned inputs, branch/worktree and dirty state, validation, dependency, pending merge/action/retry, parent blockage, and completion rollup.
- Feature/Epic observations cover owner/queue liveness, graph and dispatch progress, approvals/comments/dependencies, integration and review/publication/closeout state, stale revisions, and trunk/integration discrepancies. No-progress requires repeated authoritative evidence or an expired canonical deadline.
- Healthy observation is byte-for-byte silent across watched board, queues, ledgers, Git, events, notifications, model turns, and external success calls.
- Repeated observations, changing generations, unavailable evidence, split repositories, old unresolved completed work, missing capability, and typed identity regression are covered.
- Validation uses existing fixtures and does not rely on model or forge access; record any pre-existing provider-preflight fixture failure separately from feature behavior.

## Validation
Run focused projection/ledger integration cases and the relevant existing recovery tests; avoid duplicating low-level tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
