---
id: task_048_004_003
title: Gate recovery CI and reconcile architecture and local runbook
tier: task
status: completed
parent: feat_048_004
children: []
depends_on:
- task_048_004_002
owners:
- swe
skills: []
parent_rev: 107d3a267da1153e77d5818188e7abd19f35389d
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Gate recovery CI and reconcile architecture and local runbook

## Parent Feature

[feat_048_004](../../features/2_active/feat_048_004_gate_recovery_with_adversarial_ci_and_controlled_supervisor_evidence.md)

## Depends on

- task_048_004_002

## Acceptance criteria

- Fresh checkout setup and exact local command reproduce the acceptance selection using declared dependencies. CI proves five controlled fault mutations were detected, via retained Task 2 evidence; it never checks in a weakened gate. Measure runtime and reduce redundant fixtures or scope only with explicit coverage accounting. Preserve the existing review-recovery checks.
- Reconcile final source with root and `cascade/{task,agent,watchdog,workspace,feature,epic,war_room}/DESIGN.md` as affected. Review `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-supervisor-components`, `cascade-team-components`, affected CLI/War Room components, and integrated `cascade-task-code`, `cascade-agent-code`, `cascade-watchdog-code`, `cascade-teams-code`, tier/workspace/dashboard/http Code views. Harness adds no deployed container/store; change production relationships only when source warrants it. Keep each requirement/decision one owner; describe current behavior without delivery history.
- For actual architecture deltas, update owning DESIGN.md and `model.dsl`, `views.dsl`, `workspace.contract.json` together. Use real source symbols, declaration kinds, `cascade.codeComponent`, `cascade.parent`, `cascade.sourcePath`, `cascade.sourceSymbol`. Include execution sequence, state, restart/resume, authority and process-isolation limits. Do not rewrite accepted snapshots.
- Validate source contract, pinned local rendering, context → container → component → Code, Level up, deep-link restoration, pinned-source opening; inspect stale renamed/deleted symbols and moved owners. Measure warm artifact reuse and verify no per-view process launch or removed render bounds. Trace one normal and one failure/restart scenario. Record commands/results, designs reviewed/updated or concrete no-change reasons, performance evidence and unresolved gaps in task closeout.
- Preserve Task 1's real scoped owner journey, F3's post-push/pre-receipt and original-budget regression, Task 2's adversarial and five-mutation evidence, and existing review publication safeguards in one automatic `Recovery contract` gate. A 10-minute timeout is a failed gate; no silent skip or weaker fallback.
- Inspect `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-supervisor-components`, `cascade-team-components`, affected CLI/War Room component views, and every affected native Code view including `cascade-teams-code`, `cascade-dashboard-code` and `cascade-war-room-http-code`. Record changed source symbol/kind/owner and model/contract updates, or specific no-change evidence, for each level.

- The original `tests/test_review_health.py::test_validation_and_publication_failures_remain_owned_and_retryable` assertion stays in the mandatory selection. The production correction is now accepted on `feat/feat_048_001` at `51cffe146b8b423027266f8469678c482e321c79`: PR #251 merged as `abfe2b2089343f6167e2e46e24c3c5e35991f4ca` after green review-recovery (55 passed). Feature 004 integrated it at `111319e52bd202fdabca20bdb315fa3a5f9f2627`, retaining provider-linked validation attributes and material fingerprints, and testing actual cumulative exhaustion before requiring independent extension. Verify this integrated revision is an ancestor of the Task checkout, retain both original and added material-retry, provider nesting and numerical exhaustion safeguards, then rerun full bounded validation. The focused integrated regression selection passed four tests; the full gate still must be run. The full 10-minute-bounded Recovery contract selection must pass on the exact integrated F4 SHA; retain prior 161-passed/one-failed results as pre-correction evidence. Refresh design, Code-view, renderer/browser and dossier review after that source change. Do not weaken the test, exclude it, reset the incident budget or duplicate the production fix.

## Files likely touched

`.github/workflows/recovery-contract.yml`, `README.md`, owning DESIGN.md, `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}` only as actual architecture changes require.

## Implementation notes

## Scope
Update `.github/workflows/recovery-contract.yml` and README. Keep the check name `Recovery contract`, trigger relevant PRs and main automatically, enforce an initial 10-minute job timeout and fail on timeout. Include existing review publication regression plus Tasks 1–2 owner journey and adversarial assertions. Upload bounded sanitized failure evidence; no silent prerequisite skips or optional/manual-only acceptance path.

## Skills

_(none)_

## Test plan

Run the exact CI selection locally from a fresh checkout and in the bounded PR/main job; retain measured runtime and sanitized failure artifacts. Run source-contract validation, supported local rendering and representative browser navigation, then inspect every affected Code node and normal/failure trace.

## Out of scope

Unapproved installation, live deployment or bypass of scoped recovery and review gates.
