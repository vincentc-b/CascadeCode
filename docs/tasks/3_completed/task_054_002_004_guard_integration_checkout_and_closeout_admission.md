---
id: task_054_002_004
title: Guard integration checkout and closeout admission
tier: task
status: completed
parent: feat_054_002
children: []
depends_on:
- task_054_002_002
owners:
- swe
skills: []
parent_rev: c651365be00dc1a0e695a3cd7b212b789e125671
created: '2026-11-27'
updated: '2026-11-28'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Guard integration checkout and closeout admission

## Parent Feature

[feat_054_002](../../features/2_active/feat_054_002.md)

## Depends on

- task_054_002_002

## Acceptance criteria

1. Validate the pinned physical board and accepted terminal history before admitting a new integration checkout or using a verified closeout target. Split tracking/product roots must use the applicable canonical ownership and pinned physical evidence; unavailable evidence refuses admission.
2. Refused Epic checkout creation leaves registry, branches and checkouts unpoisoned. Recovery of interrupted or repeated provisioning remains idempotent and preserves existing owner work; no branch deletion, force push or unowned reset.
3. Accepted target and source revisions are fenced across creation, closeout and retry. Terminal descendants and exact cancelled child feedback remain present; a changed target requires fresh proof. Preserve current Task/Feature/Epic retirement authority and unrelated specifications.
4. Reconcile cascade/workspace/DESIGN.md provisioning/restart flow, cascade/boss/DESIGN.md closeout consumption, and cascade-workspace-code/cascade-boss-code nodes, relationships and source contract. Document level-specific diagram impact.

5. Validate changed cascade-workspace-code and cascade-boss-code nodes and affected component links in the revision-pinned model, views and source contract. Check cascade.codeComponent, parent/path/symbol/kind, source-contract validation and local pinned render. Traverse context → containers → components → Code, Level up, deep link and pinned source opening; check stale symbols and record measured warm reuse and render bounds. Trace normal provisioning and refusal/interrupted restart against source and record reviewed designs, all-level impact and gaps in closeout.

## Files likely touched

cascade/workspace/integration_worktree.py; cascade/workspace/closeout.py; cascade/boss/epic_complete.py; cascade/workspace/DESIGN.md; cascade/boss/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}; tests/workspace/test_integration_worktrees.py; tests/workspace/test_closeout_workspace.py; tests/boss/test_merge_targets.py.

## Implementation notes

Validate the actual accepted target and newly admitted Epic/Feature/Task checkout before registration or closeout use. Check split tracking/product roots, accepted terminal descendants and cancellation feedback; refuse unavailable/stale evidence without poisoning registry, branch or checkout. Preserve repeatable creation/resume, owner authority and unrelated specs. Use real temporary Git repositories and cover target movement and interruption; update Workspace/Boss design and Code views.

## Skills

_(none)_

## Test plan

Real temporary Git checkout tests for clean/invalid split roots, stale backlog beside completed child, cancellation, interruption/retry, repeated delivery and target movement. Check registry, refs and worktree list after refusal; run focused workspace/Boss suites and changed-view source-contract/render checks.

## Out of scope

Automatically deleting or rewriting historical copies; product trunk mutation outside existing guarded workflow.
