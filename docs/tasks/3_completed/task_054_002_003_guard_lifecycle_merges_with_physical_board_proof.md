---
id: task_054_002_003
title: Guard lifecycle merges with physical board proof
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
# Guard lifecycle merges with physical board proof

## Parent Feature

[feat_054_002](../../features/2_active/feat_054_002.md)

## Depends on

- task_054_002_002

## Acceptance criteria

1. Before guarded Task, Feature and Epic merge acceptance, verify the exact prospective result through the physical scan and accepted-history proof. Also enforce the same gate for publication without weakening exact review result identity, current source/target fencing, approval, validator profile or incident budget.
2. Refuse divergent stale backlog/completed duplicates, missing terminal descendants, conflicting cancellation feedback and target movement with exact diagnostics and owner action. A repaired result gets a new independent scan/proof; no cached green receipt crosses target revisions.
3. Preserve preflight, lifecycle lock, merge conflict, dirty-worktree and retirement authority. Failure leaves operator and team work recoverable; no force push, hard reset of another owner's checkout or automatic column-preference cleanup.
4. Reconcile cascade/workspace/DESIGN.md and cascade/boss/DESIGN.md interfaces and cascade-workspace-code/cascade-boss-code source symbols, parent component relationships and source contract for guarded merge paths. Record design impact at all levels.

5. Validate changed cascade-teams-code, cascade-workspace-code and cascade-boss-code nodes and affected component links in the revision-pinned model, views and source contract. Check cascade.codeComponent, parent/path/symbol/kind, source-contract validation and local pinned render. Traverse context → containers → components → Code, Level up, deep link and pinned source opening; check stale symbols and record measured warm reuse and render bounds. Trace accepted and refused/target-drift restart against source and record reviewed designs, all-level impact and gaps in closeout.

## Files likely touched

cascade/workspace/branch_synchronization.py; cascade/boss/merge.py; cascade/review_validation.py; cascade/workspace/DESIGN.md; cascade/boss/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}; tests/workspace/test_branch_synchronization.py; tests/boss/test_merge.py; tests/test_review_publication_safeguards.py.

## Implementation notes

Apply exact candidate physical/history validation before accepting Task, Feature and Epic branch merges and before publication. Preserve current target and source fencing, review authority, incident budgets, rollback safeguards and operator work. Refuse divergent stale backlog/completed copies, squash/rebase and stacked-history regressions with actionable diagnostics; revalidate repaired results independently. Cover no-op/replay and conflict outcomes in real Git tests; update Workspace and Boss Code views.

## Skills

_(none)_

## Test plan

Real temporary Git tests for clean/invalid Task, Feature and Epic merges, squash/rebase and stacked histories, duplicate physical IDs, repeat delivery, conflict preservation and changed target heads. Run focused guarded merge and publication suites and changed-view source-contract/render checks.

## Out of scope

Speculative repair or cleanup of another owner's checkout; live forge mutation.
