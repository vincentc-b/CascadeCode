---
id: task_051_003_004
title: Fence downstream recovery on upstream review evidence
tier: task
status: completed
parent: feat_051_003
children: []
depends_on:
- task_051_003_003
owners:
- swe
skills: []
parent_rev: 7d7866347ad3f78c939a3c96a361cfa406a3996c
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Fence downstream recovery on upstream review evidence

## Parent Feature

[feat_051_003](../../features/2_active/feat_051_003.md)

## Depends on

- task_051_003_003

## Acceptance criteria

- Downstream recovery records the exact upstream blocker/evidence generation separately from its Task failure.
- Unchanged upstream CI across polls and restart neither redispatches nor charges the downstream Task; changed evidence permits one gated reevaluation.
- Upstream verified merge releases eligible progress and unrelated downstream failure remains actionable.
- An integrated scripted-transport journey, Task/consumer design and Code source-contract/render/navigation checks pass.

## Files likely touched

- `cascade/task_rollup.py`, affected Task recovery/queued-delivery code and focused integration tests.
- `cascade/task/DESIGN.md`, affected Watchdog/root design, and architecture model, views and contract files.

## Implementation notes

Goal: fence downstream Task queued-delivery/recovery retries on a concrete upstream review blocker and its material evidence generation. Persist blocker identity and evidence generation on the affected downstream action using the existing ledger, alongside the Task's own failure identity. If upstream CI/policy evidence remains unchanged, watchdog/queued-delivery retry does not redispatch the downstream Task or spend another attempt. A changed upstream generation releases exactly one reevaluation through current dependency, ownership and recovery gates. Unrelated downstream failures stay independently actionable; restart retains the fence and pending delivery. Avoid a new ledger, scheduler or blanket suppression by parent status.

Acceptance: tests for downstream queued delivery/recovery with same upstream red check across polls and restart, new run/source/target evidence, upstream green and merge release, unrelated downstream failure, and current dependency gate. Include an integrated scripted-transport journey over production normalization and repair/postcheck paths to prove the review owner and downstream Task do not loop. Update cascade/task/DESIGN.md and consumer links in cascade/watchdog/DESIGN.md or cascade/DESIGN.md with stable IDs and source-linked retry flow; reconcile cascade-task-code, cascade-teams-code and affected component relationships in model.dsl, views.dsl and workspace.contract.json. Validate source contract, pinned render, context→container→component→Code, Level up/deep link/pinned source and normal/restart traces; record evidence/gaps in task closeout.

## Skills

_(none)_

## Test plan

Run focused downstream queued-delivery/recovery and integrated scripted-transport tests, including unchanged upstream red, changed evidence, verified release, unrelated failure and restart. Validate source contract, pinned render and changed Code navigation.

## Out of scope

No blanket suppression by parent status, new ledger/scheduler or bypass of dependency and ownership gates.
