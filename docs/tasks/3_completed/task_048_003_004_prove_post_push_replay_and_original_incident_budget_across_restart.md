---
id: task_048_003_004
title: Prove post-push replay and original incident budget across restart
tier: task
status: completed
parent: feat_048_003
children: []
depends_on:
- task_048_003_003
owners:
- swe
skills: []
parent_rev: 06fdb44b53fa9fbe26c717d0e47672ce975bdc63
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove post-push replay and original incident budget across restart

## Parent Feature

feat_048_003

## Depends on

- task_048_003_003

## Acceptance criteria

- In the existing real-repository convergence harness, interrupt the production publication path after the bare remote accepts the exact push and before local completion receipt persistence. Resume through the production owner/reconciliation API, compare authoritative remote and forge state before any replay, and prove exactly one publication, review creation, accepted action and remote effect under repeated sweeps and competing callers. Unavailable or changed authoritative evidence must remain pending with an owner and next action.
- Bind the Task-owned original incident budget before repair. Read it through `read_incident_budget` after adapter bootstrap, worker restart, remote-effect reconciliation and final independent postcheck. Assert the same incident/action identity, finite allowance, retained consumption and history, and idempotent operation reservations/settlements, including reservation reconciliation after interruption. No restart or replay may mint an allowance. Exhaust the original allowance and prove further expensive recovery is refused without resetting the incident or losing its escalation record.
- Keep the completed-parent/late-child and split product/tracking root journey, immutable validation pair, current acceptance generation and product acceptance gate. Use production tools, real temporary repositories and processes; script only external provider/forge transport. Count effects independently rather than asserting only a stored success flag.
- Fix only production behavior exposed by the proof. Reconcile changed owning designs and native C4 Code views/source contract, including Task budget ownership and shared publication where affected. Verify context-to-code navigation, Level up, deep links and pinned source for changed views; record concrete no-change reasons for unaffected levels.

## Files likely touched

tests/test_late_repair_convergence.py; focused production publication, incident-budget or reconciliation modules only if the injected failure exposes a defect; owning DESIGN.md and architecture model.dsl/views.dsl/workspace.contract.json only for actual structural changes.

## Implementation notes

The current Task 002 journey manually pushes and repeats reconciliation without an interruption between push and receipt, and it does not read the original incident budget. Preserve the existing historical incident and queued action. Coordinate final documentation conclusions with Task 003.

## Skills

- skills/design/SKILL.md

## Test plan

Run the focused injected post-push and budget/restart scenarios for both colocated and split roots, including exhausted-budget refusal, plus directly affected regression tests. Run the C4 source validator and supported render/browser navigation for changed views. Record exact commands, results, independent remote push counts, public budget snapshots and limitations in closeout.

## Out of scope

Live deployment, dependency installation, new audit dashboards or a duplicate lifecycle ledger.
