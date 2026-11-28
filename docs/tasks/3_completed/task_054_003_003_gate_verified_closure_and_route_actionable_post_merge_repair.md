---
id: task_054_003_003
title: Gate verified closure and route actionable post-merge repair
tier: task
status: completed
parent: feat_054_003
children: []
depends_on:
- task_054_003_001
- task_054_003_002
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
# Gate verified closure and route actionable post-merge repair

## Parent Feature

[feat_054_003](../../features/2_active/feat_054_003.md)

## Depends on

- task_054_003_001
- task_054_003_002

## Acceptance criteria

1. Consume exact accepted merge CI, remote physical-board proof and local sync receipts independently in cascade/boss/epic_complete.py and existing closeout/review consumers. Only a fresh matching green merge SHA, valid board, converged required trunk and completion evidence permit verified closure/retirement. Persist dimensions and current generation; interrupted observation, commit and notification rejoin without duplicate action or stale receipt promotion.
2. Extend existing Watchdog bounded producer/postcheck and Feature repair admission for post-merge red/unavailable, sync and board failures. Fixable failures get a current actionable owner under existing budgets. Completed/open-review work retains original review owner. Accepted/closed work uses a supported corrective scope on the current target with required approval and preserved original accepted lineage; if unavailable, report exact capability/approval gate. Never enqueue an unprocessable repair or reopen unchanged accepted work.
3. Cover restart, late receipt, target movement, offline forge, review-owner recovery, incident budget and human-only approval with focused real-Git/scripted-forge tests. GET/polling must not acquire mutation authority.
4. Reconcile cascade/boss/DESIGN.md, cascade/watchdog/DESIGN.md, cascade/feature/DESIGN.md and cascade/DESIGN.md interface. Update cascade-supervisor-components, cascade-team-components, cascade-boss-code, cascade-watchdog-code and cascade-feature-code for real symbols/state transitions in pinned model/views/contract. Verify normal/failure/resume, source contract, render, Code navigation and measured bounds.

## Files likely touched

cascade/boss/epic_complete.py; cascade/review.py; cascade/review_health.py; cascade/watchdog/incident_postcheck.py; cascade/feature/repair.py; cascade/boss/DESIGN.md; cascade/watchdog/DESIGN.md; cascade/feature/DESIGN.md; tests/test_review_health.py; tests/watchdog/test_parent_lifecycle_postcheck.py; tests/boss/test_epic_complete.py; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}.

## Implementation notes

Implement the focused contract above using the existing adapters, receipts and owner boundaries.

## Skills

_(none)_

## Test plan

Run the focused real-Git, scripted-forge and architecture checks named above; record exact commands, results and gaps.

## Out of scope

New scheduler, ledger, owner lifecycle or automatic human approval.
