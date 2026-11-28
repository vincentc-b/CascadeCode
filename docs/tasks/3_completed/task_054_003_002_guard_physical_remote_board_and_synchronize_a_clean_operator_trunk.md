---
id: task_054_003_002
title: Guard physical remote board and synchronize a clean operator trunk
tier: task
status: completed
parent: feat_054_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e099598be3a264c36b01f00922d70526a1692769
created: '2026-11-28'
updated: '2026-11-28'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Guard physical remote board and synchronize a clean operator trunk

## Parent Feature

[feat_054_003](../../features/2_active/feat_054_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Acceptance criteria
1. In cascade/workspace/closeout.py, integration_worktree.py and branch_synchronization.py (and the existing trunk adapter if needed), fetch the configured remote target and validate its exact physical board and accepted terminal/cancellation history before trunk or checkout admission. Split product/tracking roots use their authoritative owner evidence. Recheck target drift before mutation and refuse unavailable or stale proofs.
2. Auto fast-forward only a clean eligible checkout already on the configured trunk. Record local and remote SHAs and sync result. Dirty, diverged, conflicting or wrong-branch checkout stays byte-for-byte intact; return bounded reconciliation/preview with current heads, owner and prerequisite. No reset, force push, overwrite or stale remote-tracking-ref trust. Repeated delivery and restart are idempotent.
3. Test real temporary remote/worktree cases including target movement, split roots, completed/backlog resurrection, dirty/diverged/wrong branch and interrupted sync; inspect refs, index, files and worktree registrations after refusals.
4. Reconcile cascade/workspace/DESIGN.md and affected cascade/boss/DESIGN.md interface. Update cascade-supervisor-components, cascade-workspace-code and applicable cascade-boss-code nodes/relationships/source contract in the pinned model/views/contract. Explain fetch, physical proof, mutation fence, persistence and recovery. Validate C4 navigation, source links, contract and render; record all-level impact and measured checks.

## Files likely touched
cascade/workspace/closeout.py; cascade/workspace/integration_worktree.py; cascade/workspace/branch_synchronization.py; cascade/tracking.py; cascade/workspace/DESIGN.md; cascade/boss/DESIGN.md; tests/workspace/test_closeout_workspace.py; tests/workspace/test_branch_synchronization.py; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}.

## Out of scope
Discarding operator changes or rewriting accepted history.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
