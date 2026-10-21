---
id: task_003
title: Reconcile approval-driven dispatch after restart and add focused integration coverage
tier: task
status: completed
parent: feat_001
children: []
depends_on:
- task_002
owners:
- swe
skills: []
parent_rev: d5ddbeec62e57c1ae9a6b4b88a9f0625625ceb5d
created: '2026-10-21'
updated: '2026-10-21'
---
# Reconcile approval-driven dispatch after restart and add focused integration coverage

## Parent Feature

[feat_001](../../features/2_active/feat_001.md)

## Depends on

- task_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Make startup/reconciliation drive the same central dispatch eligibility path and prove the end-to-end contract with economical integration tests.

## Scope
- During reconciliation, load durable approval state and re-evaluate undispatched features through the canonical dispatch path.
- Reuse existing dispatch identity/idempotency mechanisms so restart cannot duplicate work.
- Add focused integration scenarios for explicit feature approval, epic approval of current children, dependency blocking/unblocking, merge-gate blocking/unblocking, and restart recovery.
- Prefer scenario-level assertions over redundant mock-heavy unit coverage.

## Acceptance
- Restart neither loses an eligible dispatch nor repeats an already-recorded dispatch.
- Approval is not re-applied with duplicate side effects.
- Tests demonstrate every feature acceptance criterion, including later epic children remaining unapproved.
- No completion rollup, dashboard, or alternate dispatch/store behavior is added.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
