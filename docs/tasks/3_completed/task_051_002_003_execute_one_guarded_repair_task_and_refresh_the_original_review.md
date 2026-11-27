---
id: task_051_002_003
title: Execute one guarded repair Task and refresh the original review
tier: task
status: completed
parent: feat_051_002
children: []
depends_on:
- task_051_002_002
owners:
- swe
skills: []
parent_rev: f834c5c379eaa970b2d29e938d582ab00d8b5858
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Execute one guarded repair Task and refresh the original review

## Parent Feature

[feat_051_002](../../features/2_active/feat_051_002_admit_durable_scoped_repairs_for_open_feature_reviews.md)

## Depends on

- task_051_002_002

## Acceptance criteria

- The retained Feature can use its scoped `mint_task`, normal dispatch, validation and guarded publication tools only for a current admitted review-repair action. `reserve_repair_child` persists one Task ID, request digest and rendered-spec digest before Task or parent writes; replay after either write returns the same child and repaired parent linkage.
- A duplicate request or concurrent turn cannot create another child, writer, review or provider/validation attempt. Changed content under the same request ID refuses. Existing incident claim and finite provider/validation budget identities remain bound across restart.
- A scoped repair Task can address the review's own fix request while that request is unresolved; unrelated governing comments, changed approval/scope, cancellation, dependencies or stale heads produce typed prerequisites. Broader changes use amendment/approval paths.
- Publication updates the original Feature branch and same review identity/URL using current head and review-generation gates, and preserves existing publication safeguards. Accepted/merged review follow-up remains outside this route.
- Reconcile `cascade/feature/DESIGN.md` and affected Task/teams/package designs with normal, refusal and restart flows. Update `cascade-feature-code` and only source-affected `cascade-task-code`/`cascade-teams-code` nodes and relationships in model.dsl, views.dsl and workspace.contract.json; record concrete no-change reasons for unaffected views. Verify declaration kinds, links and context → Code navigation, Level up, deep link and pinned source.

## Files likely touched

`cascade/feature/mint.py`, `cascade/feature/repair.py`, scoped registry/wiring and publication path; Task validation or provider budget code only if its contract changes; owning designs and architecture source closure.

## Implementation notes

Use normal guarded Task and publication tools, not a dedicated repair executor or second ledger. Preserve the original source/target route and claim token from admission.

## Skills

_(none)_

## Test plan

Extend `tests/feature/test_repair.py`, mint reservation and review publication safeguard suites with real temporary Git and scripted forge. Inject crashes around reservation, Task write, parent write and publication checkpoint, plus concurrent workers. Assert a single child/review and unchanged finite budgets on replay. Run source-contract validation and pinned render/navigation checks, recording actual evidence and gaps.

## Out of scope

Cross-forge required-check normalization, independent terminal postcheck, new PR creation and UI controls.
