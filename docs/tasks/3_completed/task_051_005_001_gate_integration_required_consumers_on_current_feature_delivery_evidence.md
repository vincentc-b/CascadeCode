---
id: task_051_005_001
title: Gate integration-required consumers on current Feature delivery evidence
tier: task
status: completed
parent: feat_051_005
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 23353975c7124661b440c16976a619df17904268
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Gate integration-required consumers on current Feature delivery evidence

## Parent Feature

[feat_051_005](../../features/2_active/feat_051_005.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Acceptance criteria

- Reproduce the closed-unverified Feature review discrepancy on temporary Git using ordinary configured approval/activation. Show delivery phase merge_verification_pending and blocker accepted_current_generation_missing while the existing review-pending and Watchdog dependency checks incorrectly report readiness.
- Inventory every integration-required execution consumer in cascade/watchdog/dispatch.py, cascade/stacked_dispatch.py, Boss view and recovery dispatch. Trace each decision to the current review/target evidence. Keep cascade/dependency_evaluation.py planning readiness independent.
- Make integration-required consumers wait on closed-unmerged, missing, stale-generation and accepted-but-not-intended-target-integrated review evidence. Preserve deliberate stacked dispatch where its contract allows execution. Current verified intended-target integration releases eligible execution exactly once through the ordinary gates.
- Add focused real-Git tests for each state and for the stacked exception. Do not bypass activation, approval, CI or review ownership.
- Reconcile affected cascade/watchdog/DESIGN.md, cascade/boss/DESIGN.md, cascade/feature/DESIGN.md and cascade/DESIGN.md with actual code. Update cascade-supervisor-components/cascade-team-components and affected cascade-watchdog-code/cascade-boss-code/cascade-feature-code nodes in model.dsl, views.dsl and workspace.contract.json using real symbols and native declaration kinds. Record concrete unchanged-level reasons and source-contract/render/navigation evidence in closeout.

## Likely source and tests

cascade/review.py, cascade/watchdog/dispatch.py, cascade/stacked_dispatch.py, cascade/boss/view.py, relevant recovery dispatch; focused watchdog/stacked/Boss integration tests.

## Limits

No new planner semantics, provider launcher, review, ledger, installation or deployment.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
