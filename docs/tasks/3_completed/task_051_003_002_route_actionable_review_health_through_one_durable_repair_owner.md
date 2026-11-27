---
id: task_051_003_002
title: Route actionable review health through one durable repair owner
tier: task
status: completed
parent: feat_051_003
children: []
depends_on:
- task_051_003_001
owners:
- swe
skills: []
parent_rev: 7d7866347ad3f78c939a3c96a361cfa406a3996c
created: '2026-11-26'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route actionable review health through one durable repair owner

## Parent Feature

[feat_051_003](../../features/2_active/feat_051_003.md)

## Depends on

- task_051_003_001

## Acceptance criteria

- Failed required checks or actionable feedback route even when mergeability is clean; conflicts and failed checks on one review share one Feature repair owner.
- Pending, missing, stale, unknown policy, approval-only and transient cases are typed waits with no provider turn.
- Identical evidence across polls and restart reuses the action, Task and budgets; changed head, check-run or feedback identity permits one bounded reevaluation.
- Existing guarded publication, human merge policy, source-linked Watchdog design/Code view, source-contract validation, pinned render and navigation remain verified.

## Files likely touched

- `cascade/review_health.py`, existing resolution-action and Feature repair routing, focused review-health/rebase, resolution-action and reservation tests.
- `cascade/watchdog/DESIGN.md`, `cascade/DESIGN.md`, and affected `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`.

## Implementation notes

Goal: extend cascade/review_health.py and existing resolution-action/Feature repair routing to classify normalized open-review evidence. A mergeable review with a failed required check or actionable feedback is unhealthy; pending/missing/stale checks, unknown policy, approval-only waits and transient forge failures are typed non-provider waits. Conflict and failed checks for the same original review/current repair generation converge on one Feature-owned repair request. Define material identity from original review, source/target head pair, failing check/run or feedback identity and repair generation; persist it in existing action/incident records. Unchanged polling and restart rejoin the same action and retain claim/incident budgets. Changed material evidence permits one bounded reevaluation through existing gates. Preserve guarded conflict validation/republication and human merge policy; never rerun CI or open a replacement review.

Acceptance: review-health/rebase, resolution-action and reservation tests prove each classification, no second Task/model turn/budget reset for identical evidence, changed evidence reevaluation, no competing conflict and CI writers, restart with pending delivery, and no provider on transient/pending/unchanged polling. Update cascade/watchdog/DESIGN.md with stable owned IDs, source-linked sequence and unknown/human/restart path; reconcile cascade/DESIGN.md interface link and affected cascade-watchdog-code and cascade-teams-code nodes/relationships in model.dsl, views.dsl and workspace.contract.json. Verify source contract, pinned render, Code navigation/Level up/deep link/pinned source and normal/failure traces; record evidence and gap in task closeout.

## Skills

_(none)_

## Test plan

Run focused review-health/rebase, resolution-action and reservation tests for normal, unknown/human and restart paths. Validate source contract, pinned render, and changed Code navigation, Level up, deep link and pinned source.

## Out of scope

No new scheduler/ledger, blind CI rerun, arbitrary forge command, replacement review or protection bypass.
