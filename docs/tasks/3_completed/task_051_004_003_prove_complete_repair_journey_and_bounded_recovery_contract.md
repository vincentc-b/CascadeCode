---
id: task_051_004_003
title: Prove complete repair journey and bounded recovery contract
tier: task
status: completed
parent: feat_051_004
children: []
depends_on:
- task_051_004_002
owners:
- swe
skills: []
parent_rev: 0733fb8f15da227daad2bccfbb89027889c43734
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove complete repair journey and bounded recovery contract

## Parent Feature

[feat_051_004](../../features/2_active/feat_051_004.md)

## Depends on

- task_051_004_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope and acceptance
Extend tests/test_late_repair_convergence.py and tests/test_review_recovery_journey.py with one complete production-orchestration journey using real temporary Git repositories, original Feature branch/PR identity, a parent repair request, durable admitted Task on that branch, guarded validation/publication, scripted fresh green CI, human-policy-compatible merge observation into the Epic, independent postcheck and only then retirement. Script only forge/check/provider transport and identify those seams in test evidence. Assert no duplicate Task or PR, no manual board edits, no approval bypass, retained comments, checkpoint/history survival, no unchanged idle provider turn and no downstream rerun storm. Include split product/tracking roots.

Cover target movement/conflict, actionable feedback, stale and duplicate request, restart after admission before wake, one-writer concurrent repairs, missing forge/check policy, required human approval, budget exhaustion, cancellation/closed-unmerged and legacy completed-open review. Assert changed source/check generation cannot inherit old green; terminal state requires current evidence and intended-target merge. Extend existing harness instead of copying a large second fixture. Run focused suites and the bounded .github/workflows/recovery-contract.yml command; add the new journey to that gate only if not already included.

## Design handoff
Reconcile implementation changes in their owning DESIGN.md and C4 source contract as they occur. Trace normal and failure/restart paths across Feature, Watchdog, Boss, Task and War Room design links, routing any outside-scope owner gap through the parent artifact. Update affected model.dsl, views.dsl and workspace.contract.json together with real source symbols/kinds and codeComponent/parent metadata. Record baseline versus new acceptance, source validation, pinned render, actual context→container→component→Code navigation, Level up, deep link, pinned source and material limitations. Preserve accepted snapshots.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
