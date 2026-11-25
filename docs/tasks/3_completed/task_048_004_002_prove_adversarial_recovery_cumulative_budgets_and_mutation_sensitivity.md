---
id: task_048_004_002
title: Prove adversarial recovery, cumulative budgets and mutation sensitivity
tier: task
status: completed
parent: feat_048_004
children: []
depends_on:
- task_048_004_001
owners:
- swe
skills: []
parent_rev: 61f74c66d0054db91b6bc6177c1a49b7b096a07c
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove adversarial recovery, cumulative budgets and mutation sensitivity

## Parent Feature

[feat_048_004](../../features/2_active/feat_048_004_gate_recovery_with_adversarial_ci_and_controlled_supervisor_evidence.md)

## Depends on

- task_048_004_001

## Acceptance criteria

- Actual red tests, insufficient budget, malformed or infeasible policy, policy/source/target drift during checks, stale admission, competing remote update, dirty/uncommitted checkout, live owner, wrong scope, absent capability, denied approval/credential and unavailable evidence all retain the original obligation and a typed refusal or named wait. Failed or unverifiable checks cannot resolve or publish.
- Prove one unchanged expensive failure; transient total cap and backoff; paid-turn/model-runtime and process allowance; concurrent atomic reservation; unknown usage; in-flight overrun/cancellation. Restart, new generation, cosmetic revision, provider switch, policy cycle and replacement action preserve cumulative history and do not mint allowance. Repeated audit requests coalesce after exhaustion. Refused and independently authorized finite extensions retain prior attempts/consumption. Count real physical invocations and worker/Task/review/message/publication effects independently.
- Run five separate controlled fault mutations against deduplication, validation, immutable tested-SHA publication, independent postcheck and receipt recovery. Each must fail its relevant focused test. Restore source after each mutation; never leave weakened production checks or accepted snapshots. Record mutation, test command, failing assertion and clean restoration.
- Architecture: verify the same context/container/component boundaries as Task 1; reconcile changed budget/admission, provider adapter, watchdog, publication and postcheck declarations in `cascade-task-code`, `cascade-agent-code`, `cascade-watchdog-code`, `cascade-teams-code` and affected tier/workspace Code views. Task, Agent, Watchdog, package and Workspace designs own state/restart/failure flows. Update `model.dsl`, `views.dsl`, `workspace.contract.json` and owning DESIGN.md together only for actual source deltas, with real symbols/kinds and `cascade.parent`/`cascade.sourcePath`/`cascade.sourceSymbol`; otherwise document precise no-change. Verify source/render/navigation, pinned source and normal/failure traces.
- Record focused tests, design review, actual verification and gaps in task closeout.
- Bind every refusal to the original incident, material generation, claim, operation and policy version. Compare `ReservationDecision.state/reason`, `IncidentOperationDecision.state/reason`, provider `ProviderBudgetRefusedError` and publication `recovery_state/reason` with physical transport/process/remote counters. Preserve known, estimated and unavailable usage as distinct evidence.
- Inspect `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-supervisor-components`, `cascade-team-components`, and affected `cascade-cli-components`/`cascade-war-room-components`; for Code inspect `cascade-task-code`, `cascade-agent-code`, `cascade-watchdog-code`, `cascade-teams-code`, and affected Epic/Feature/Workspace/Dashboard/War Room HTTP views. Record per-view changed symbols/kinds/owners or a source-backed no-change result.

## Files likely touched

`tests/test_late_repair_convergence.py`, `tests/task/test_incident_budget.py`, `tests/agent/test_provider_recovery_contract.py`, `tests/test_review_publication_safeguards.py`; owning DESIGN.md and architecture source only if source changes require them.

## Implementation notes

## Scope
Extend the shared harness from Task 1 and nearby high-signal tests, reusing `tests/task/test_incident_budget.py`, `tests/agent/test_provider_recovery_contract.py`, `tests/test_review_publication_safeguards.py` and `tests/test_late_repair_convergence.py`. Exercise real admissions, scoped adapters and process/remote effects. Add only scenarios needed to close Epic 048 criteria 12, 16–19 and the feature matrix.

## Skills

_(none)_

## Test plan

Run focused real-repository, budget, provider and publication tests with exact commands; execute five separate temporary fault mutations, retaining each failed assertion and a clean rerun after restoration. Measure the positive journey against the finite default policy and record process/effect counters independently.

## Out of scope

Unapproved installation, live deployment or bypass of scoped recovery and review gates.
