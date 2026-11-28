---
id: task_054_003_005
title: Prove incident recovery and reconcile architecture against final code
tier: task
status: completed
parent: feat_054_003
children: []
depends_on:
- task_054_003_004
owners:
- swe
skills: []
parent_rev: f4683ee06383f5391cb26d9654323a7fc1b4092c
created: '2026-11-28'
updated: '2026-11-28'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove incident recovery and reconcile architecture against final code

## Parent Feature

[feat_054_003](../../features/2_active/feat_054_003.md)

## Depends on

- task_054_003_004

## Acceptance criteria

1. Add high-signal real temporary remote/worktree journeys using production review/sync adapters and scripted forge transport to the existing Recovery contract selection. Reproduce source-green/changed-target boot failure, stale completed/backlog resurrection poisoning new Epic, and same-second equal-size source/cache false result. Each first fails the intended assertion, yields correct repair tree/owner, then proves fresh exact merged CI green and matching remote/local trunk plus physical board. Confirm no history loss or unintended operator checkout mutation.
2. Exercise target movement, restart, offline forge, dirty/diverged main, split roots, duplicate delivery, stale receipt, review-owner recovery and human approval gates through focused scenarios; avoid a parallel test framework. For Epic verified closure, bind the supplied merge, CI, board and sync proof to the exact observed review generation, URL, route and observation identity at the atomic registry write; propagate a rejected write. Check blocker and terminal snapshot writers too. Reproduce an intervening generation/observation advance with a focused regression, or establish and test exclusion across every writer and caller. Keep the old generation unverified and preserve the new one. Record exact commands, outcomes and any residual gap.
3. Review final diff against DESIGN.md, cascade/DESIGN.md, cascade/boss/DESIGN.md, cascade/workspace/DESIGN.md, cascade/watchdog/DESIGN.md, cascade/feature/DESIGN.md and cascade/war_room/DESIGN.md. Give each requirement/decision one owner, current-fact wording, source-linked implementation, execution/recovery behavior, inspectable evidence and resolved parent/child interfaces. Root summarizes links only. Close design gaps in owned scope.
4. Reconcile authoritative model.dsl, views.dsl, workspace.contract.json and every affected cascade-supervisor-components, cascade-team-components, cascade-war-room-components and integrated Boss/Workspace/Watchdog/Feature/Dashboard/War Room HTTP Code view. Verify cascade.codeComponent, parent/path/symbol/kind, source contract, local pinned render, context→containers→components→Code, Level up/deep link/pinned source, stale symbols, warm reuse and render bounds. Record measured all-level diagram-impact inventory and concrete unchanged reasons; do not rewrite accepted snapshots.

## Files likely touched

tests/test_late_repair_convergence.py; tests/test_review_recovery_journey.py; focused Boss closure and Recovery contract tests; cascade/boss/epic_complete.py; cascade/review.py; affected DESIGN.md files; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}; docs/task_artifacts/.

## Implementation notes

Implement the focused contract above using the existing adapters, receipts and owner boundaries.

## Skills

_(none)_

## Test plan

Run the focused real-Git, scripted-forge and architecture checks named above; record exact commands, results and gaps.

## Out of scope

Live forge mutation and full repository suite as default gate.
