---
id: task_051_001_003
title: Wake retained Feature owners and verify retirement
tier: task
status: completed
parent: feat_051_001
children: []
depends_on:
- task_051_001_002
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
# Wake retained Feature owners and verify retirement

## Parent Feature

[feat_051_001](../../features/2_active/feat_051_001.md)

## Depends on

- task_051_001_002

## Acceptance criteria

- An idle open-review owner retains Feature ID, original PR, branch/path, queue and checkpoint. Repeated unchanged review/queue polls start zero role turns; a generic message never admits Task minting. New admitted repair/review event or interrupted delivery resumes the same Feature graph under one writer and advances durable cursor once; restart and concurrent stale job recheck the same eligibility.
- Retirement refuses open, unknown, closed-unmerged, stale or unsynchronized review evidence without removing branch, checkout or registry; after exact current-generation acceptance and intended-Epic proof, existing descendant, cleanliness, lock and transcript gates still apply. Preserve local/review-disabled and cancellation behavior.
- Extend tests/workspace/test_completed_recovery_kickoff.py, test_kickoff.py, test_integration_worktrees.py and a focused end-to-end completion journey using real temporary Git. Prove open review + all children, duplicate idle polls, authorized wakeup, restart, missing evidence, corrected head, verified merge and only-then retirement.
- Reconcile cascade/workspace/DESIGN.md and root DESIGN.md summary, plus affected cascade/DESIGN.md/Boss links. Update model.dsl, views.dsl and workspace.contract.json for cascade-workspace-code and affected cascade-supervisor-components/cascade-team-components relationships. Each changed Code node must link real source/symbol with correct declaration kind and semantic parent. Validate source contract and pinned local render; verify actual context → container → component → Code, Level up, deep-link restore and pinned source, then record normal/failure/restart traces and concrete no-change reasons for unaffected landscape/container levels in closeout. Do not rewrite accepted snapshots.

## Files likely touched

- `cascade/workspace/kickoff.py`, `cascade/workspace/integration_worktree.py` if proof needs it, focused tests, `cascade/workspace/DESIGN.md`, root `DESIGN.md`, and the pinned architecture model, views and source contract.

## Implementation notes

Use the shared Feature delivery view in cascade/workspace/kickoff.py ordinary delivery, startup resume and locked invocation recheck. Keep a review-pending completed-path Feature registered and wakeable for a new actionable authorized event, current admitted repair or interrupted checkpoint. Align cascade/workspace/integration_worktree.py retirement proof with terminal delivery evidence where required. Do not add a scheduler, recovery ledger or provider launcher.

## Skills

_(none)_

## Test plan

Run the focused test files named above, source-contract validation, and the supported pinned local architecture render. Record actual commands and results in closeout.

## Out of scope

New schedulers, recovery ledgers, provider launchers, approval bypasses, additional review creation for an already-open original review, and dependency installation.
