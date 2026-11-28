---
id: task_054_003_001
title: Verify exact accepted merge CI and persist independent evidence
tier: task
status: completed
parent: feat_054_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: a782f5b4c5736a2978d53cff6514a3a694a21427
created: '2026-11-28'
updated: '2026-11-28'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify exact accepted merge CI and persist independent evidence

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
1. In cascade/tracking.py and cascade/review.py, fetch fresh intended remote target identity and exact accepted merge SHA for GitHub/GitLab through existing scripted adapters. Query required check policy and all result pages for that SHA, preserving check identity and newest generation. Source or later-head green cannot satisfy merge CI; unknown policy, incomplete pagination, offline forge or missing/changed merge identity remains unavailable. Prove supported squash/rebase/stacked acceptance with current forge identity plus content/lineage, never ancestry alone.
2. Persist separate prospective result, accepted merge identity, post-merge CI pending/red/green/unknown, and observed target SHA in current review generation/registry receipts. Bound payloads; atomic generation-aware writes and replay prevent late callbacks from replacing newer evidence. Carry exact revisions and typed prerequisites to consumers.
3. Use real temporary Git repositories and scripted production forge transports for changed target, incomplete pages, newer failed generation, duplicate callback, restart and stale receipt.
4. Reconcile cascade/DESIGN.md shared evidence and cascade/boss/DESIGN.md acceptance interfaces. Update cascade-supervisor-components, cascade-team-components and applicable cascade-boss-code plus actual tracking/review owner Code nodes in authoritative model.dsl, views.dsl and workspace.contract.json. Link source symbols and current sequence/persistence/failure behavior; preserve accepted snapshots. Validate source contract, pinned local render, C4 navigation and source links; record all-level impact and measured checks.

## Files likely touched
cascade/tracking.py; cascade/review.py; cascade/DESIGN.md; cascade/boss/DESIGN.md; tests/test_tracking_find.py; tests/feature/test_review_generations.py; tests/test_epic_review_state.py; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}.

## Out of scope
New forge client, scheduler or CI runner; human merge authority.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
