---
id: task_051_005_002
title: Fence dependent Feature Task recovery on upstream review generations
tier: task
status: completed
parent: feat_051_005
children: []
depends_on:
- task_051_005_001
owners:
- swe
skills: []
parent_rev: 04edd7165032c8e52d8451b0e88e5fa4cfdc6aea
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Fence dependent Feature Task recovery on upstream review generations

## Parent Feature

[feat_051_005](../../features/2_active/feat_051_005.md)

## Depends on

- task_051_005_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Acceptance criteria

- Trace the production path from an upstream Feature's normalized red CI through Watchdog review health, dependent Feature dispatch, Task queued delivery, retry and provider/validation launch. Document the exact cross-Feature gap before changing routing.
- Route the upstream blocker identity and material evidence generation to the queued actions of affected dependent Feature Tasks only when source/target and dependency ownership prove the relationship. Keep the observation separate from each Task's own failure classification, action attempts and finite incident budget.
- Reuse the existing action metadata and guarded retry boundary. Across repeated supervisor passes and restart, unchanged red CI causes no repeated Task execution, validation, merge or charged recovery attempt. A changed material generation admits one ordinary gated reevaluation; verified intended-target release permits eligible work once. Unrelated Task failures remain independently actionable.
- Add focused real-Git tests spanning the cross-Feature path, repeated red checks, restart, changed run/head/target evidence, verified release and unrelated failure. Script forge/provider transport only at named external seams; retain ordinary activation/approval and existing Recovery budget gates.
- Reconcile cascade/task/DESIGN.md and cascade/watchdog/DESIGN.md, plus root/Feature/Boss consumers where interfaces change. Update cascade-team-components and affected cascade-task-code/cascade-watchdog-code/other owning Code views with source-linked symbols and native declaration kinds in model.dsl, views.dsl and workspace.contract.json. Trace normal, failure and restart behavior; record checks and specific no-change reasons in closeout.

## Likely source and tests

cascade/task_rollup.py, cascade/review_health.py, relevant watchdog/recovery routing; tests/task/test_rollup_queue.py, tests/test_late_repair_convergence.py and focused cross-Feature integration tests.

## Limits

No new scheduler or ledger, blanket parent-status suppression, repeated review publication, CI bypass or provider launcher.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
