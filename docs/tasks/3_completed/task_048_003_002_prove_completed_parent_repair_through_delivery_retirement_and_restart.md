---
id: task_048_003_002
title: Prove completed-parent repair through delivery, retirement and restart
tier: task
status: completed
parent: feat_048_003
children: []
depends_on:
- task_048_003_001
owners:
- swe
skills: []
parent_rev: a4a20bd3e791e251f3882a60b1314bcbd58cb5b6
created: '2026-11-24'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove completed-parent repair through delivery, retirement and restart

## Parent Feature

feat_048_003

## Depends on

- task_048_003_001

## Acceptance criteria

- Extend the existing late-repair convergence journey through production Watchdog admission, Feature owner tools, Task validation/queued delivery, review publication, parent integration, descendant-safe retirement and independent original-incident postcheck. Use real temporary repositories, a bare remote, durable stores and a worker process loaded from the reviewed repair revision established by task_048_003_001. Script only external paid provider and forge transport; use their normal production adapters and real refusals/results.
- Exercise a repair to a recovery adapter itself and split product/tracking roots. Bind immutable Task validation pairs and current repair/review acceptance generations at the accepted heads. After cleanup and process restart, assert agreement among canonical board, execution/action record, pending delivery, exact mutation owner, review registry, loaded capability generation and the original historical incident. Preserve the original incident as a candidate until the independent postcheck proves its obligation.
- Inject a crash after remote push but before local completion receipt. Reconcile the remote effect and finish the existing action without a second publication. Count worker starts, Task executions, review creations, messages, pushes and incident closures independently under repeat sweeps and competing callers.
- A live owner, changed target/source, stale admission, dirty checkout, denied authority, unavailable authoritative evidence, outstanding product acceptance or unintegrated follow-up head remains pending with the correct owner and next action. Review validation success alone cannot satisfy product acceptance or close the original incident. Fix only integration gaps this journey exposes; retain existing late-child and owner/retirement implementations.

## Diagram-impact acceptance

| Level / view | Required reconciliation |
|---|---|
| `cascade-landscape`, `cascade-context`, `cascade-containers` | Check actual operator/forge/provider, split-root and worker/process/storage boundaries; update changed relationships or record concrete no-change reasons grounded in the diff. |
| `cascade-supervisor-components`, `cascade-team-components` | Explain Watchdog admission, Feature repair, Task delivery, Boss integration, Workspace retirement, review publication and independent postcheck with their actual owning components. |
| `cascade-watchdog-code`, `cascade-feature-code`, `cascade-task-code`, `cascade-workspace-code`, and `cascade-teams-code` for shared publication | Trace `dispatch_audit_recovery`, `feature_repair`, `recover_task`, `retry_pending_task_merges`, `reconcile_parent_lifecycle_incident`, owner/retirement and shared publication symbols. Trace the remote-effect reconciliation and original incident budget through the production publication pipeline. Link actual source declarations and kinds; update model.dsl, views.dsl and workspace.contract.json together where structure changes. |
| Owning-design behavior | Reconcile cascade/watchdog, feature, task, workspace and package DESIGN.md normal/failure/restart flow, durable receipt state, remote-effect replay, authority and process isolation limits. Verify source contract, local render, Context → Containers → Components → Code, Level up, deep links and representative pinned source. |

## Files likely touched

tests/test_late_repair_convergence.py or a focused companion harness; production cascade/watchdog, cascade/feature, cascade/task, cascade/review.py, cascade/workspace integration gaps demonstrated by the journey; affected owning DESIGN.md files; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json} for changed structure.

## Implementation notes

Reuse REQ-WORKSPACE-OWNER-001, REQ-WORKSPACE-RETIRE-001, REQ-TASK-DELIVERY-002 and REQ-WATCHDOG-REPAIR-001. Do not add a duplicate late-child state machine, dashboard, raw success setter or direct lifecycle-file edits. An unverified remote effect is an obligation to reconcile, not success.

## Skills

- skills/design/SKILL.md

## Test plan

Run the normal cross-stage journey, restart/retirement and split-root variants, post-push lost-receipt replay, and focused pending/refusal cases. Run focused existing Feature/Task/Watchdog/Workspace regression tests for changed paths. Count external effects independently and verify the affected architecture views.

## Out of scope

Dependency installation, live deployment and duplicate audit projection work.
