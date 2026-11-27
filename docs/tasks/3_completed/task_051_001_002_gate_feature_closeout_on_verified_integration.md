---
id: task_051_001_002
title: Gate Feature closeout on verified integration
tier: task
status: completed
parent: feat_051_001
children: []
depends_on:
- task_051_001_001
owners:
- swe
skills: []
parent_rev: 39f310304155db0ab23629653b611c1337bbcf73
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Gate Feature closeout on verified integration

## Parent Feature

[feat_051_001](../../features/2_active/feat_051_001.md)

## Depends on

- task_051_001_001

## Acceptance criteria

- All children completed plus an open original PR retains the same owner and integration blockers. The completed-path fast path returns pending without FeatureCompleted or worktree retirement, including generation-zero legacy records.
- Green checks or a forge merged flag alone do not satisfy intended-target integration; stale source/target heads and unknown/closed-unmerged evidence refuse closeout. Exact corrected current-generation acceptance plus target proof completes once; duplicate reconciliation emits one event.
- Review-disabled/local integration still completes with its existing proof. Supported cancellation retains cleanup and parent-disposition gates. Failed closeout leaves branch, review, registry and queue available.
- Extend tests/boss/test_rollup.py, tests/boss/test_completion_reconcile.py and tests/test_completion_rollup_integration.py with a real temporary Git target where ancestry/merge identity matters; exercise open, merged-but-unsynced, corrected head, duplicate and local paths.
- Reconcile cascade/boss/DESIGN.md and affected cascade/DESIGN.md links; update model.dsl, views.dsl and workspace.contract.json for cascade-boss-code nodes/relationships. Trace normal and refusal paths against source, validate contract and pinned render, and record source-linked design review and actual verification in closeout.

## Files likely touched

- `cascade/boss/rollup.py`, relevant review consumer tests, `cascade/boss/DESIGN.md`, and the pinned architecture model, views and source contract.

## Implementation notes

Consume the shared Feature delivery projection in cascade/boss/rollup.py. Keep implementation staging for review publication, but make current-generation acceptance and independent intended-Epic integration prerequisites for normal FeatureCompleted and retirement. Preserve existing approval, comment, child delivery, repair lease, stacked review, local integration and cancellation gates.

## Skills

_(none)_

## Test plan

Run the focused test files named above, source-contract validation, and the supported pinned local architecture render. Record actual commands and results in closeout.

## Out of scope

New schedulers, recovery ledgers, provider launchers, approval bypasses, additional review creation for an already-open original review, and dependency installation.
