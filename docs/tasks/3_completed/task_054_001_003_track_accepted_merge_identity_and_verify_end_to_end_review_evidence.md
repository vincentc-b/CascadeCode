---
id: task_054_001_003
title: Track accepted merge identity and verify end-to-end review evidence
tier: task
status: completed
parent: feat_054_001
children: []
depends_on:
- task_054_001_002
owners:
- swe
skills: []
parent_rev: 25ae27aebc7fbe1c4726e7502073d72a3554ebfb
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Track accepted merge identity and verify end-to-end review evidence

## Parent Feature

[feat_054_001](../../features/2_active/feat_054_001.md)

## Depends on

- task_054_001_002

## Acceptance criteria
- Add only necessary fields to cascade/review.py and cascade/tracking.py so a review snapshot and durable acceptance record retain actual accepted merge SHA, target branch, review URL/generation and exact candidate proof identity separately. Squash, rebase and stacked deliveries cannot use ancestry, source-only green CI, or a candidate tree as proof of the accepted merge. Missing/unknown/conflicted actual identity fails closed. Exact merged-revision CI remains a later consumer obligation; human forge protections and merge authority remain unchanged.
- Pre-publication/acceptance and later actual-merge verification use one shared exact-result receipt matcher. A changed target, source, profile, environment, result or review generation invalidates reuse. Duplicate callbacks and restart do not create a second review, run a deterministic failing candidate again, or bypass the incident allowance.
- Focused real-repository and scripted-forge regressions cover normal, incompatible Task boot contract, squash/rebase/stacked acceptance, target drift, missing merge SHA, timeout/restart and A-B-A material. Tests near tests/test_late_repair_convergence.py, tests/test_review_publication_safeguards.py, tests/test_review_rebase.py and incident-budget tests; no live forge mutation or full-suite mandate. Record exact test commands and outcomes.
- Reconcile cascade/DESIGN.md, cascade/boss/DESIGN.md and cascade/task/DESIGN.md against the final diff; update cascade/workspace/DESIGN.md if its interface changed. Keep one owner per requirement/decision, source-linked module/type structure, candidate and accepted-merge sequence, persistence/restart/failure gates and current-fact wording. Extend cascade-supervisor-components and cascade-team-components and the existing cascade-teams-code owner; cascade-boss-code only for review orchestration, cascade-task-code only for budget/admission and cascade-workspace-code only for materialization. Update authoritative model.dsl, views.dsl, workspace.contract.json together, without rewriting accepted snapshots. Verify source contract, local pinned render, context → container → component → Code navigation, Level up/deep-link/source opening, stale symbols, warm artifact reuse and render bounds; record measured evidence and gaps. Root context/container need no edit absent a changed boundary.


## Files likely touched

TBD.

## Implementation notes

## Purpose
Make review acceptance and later merge verification consume the same exact-result contract while retaining the actual forge merge identity as separate evidence. Close focused integration and architecture checks.

## Skills

_(none)_

## Test plan

Run focused real-Git and scripted-forge review regressions near tests/test_late_repair_convergence.py, tests/test_review_publication_safeguards.py, tests/test_review_rebase.py and incident-budget tests; record commands, outcomes, source contract/render/navigation evidence, and any gaps.

## Out of scope

Human forge protection or merge authority, a new ledger or allowance, and actual merged-revision CI policy belong outside this Task.
