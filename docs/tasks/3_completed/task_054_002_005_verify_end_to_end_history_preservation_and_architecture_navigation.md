---
id: task_054_002_005
title: Verify end-to-end history preservation and architecture navigation
tier: task
status: completed
parent: feat_054_002
children: []
depends_on:
- task_054_002_003
- task_054_002_004
owners:
- swe
skills: []
parent_rev: a0e4cae9d1ab03224f715e0fbd5774b8cda46ce4
created: '2026-11-27'
updated: '2026-11-28'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify end-to-end history preservation and architecture navigation

## Parent Feature

[feat_054_002](../../features/2_active/feat_054_002.md)

## Depends on

- task_054_002_003
- task_054_002_004

## Acceptance criteria

1. Exercise one real Git journey from exact candidate through scan, history proof, merge/checkout admission and independent repaired candidate. Cover clean/invalid results, split roots, squash/rebase/stacked histories, cancellation, moved records, repeat delivery and target drift; accepted physical boards contain one copy per ID and retain terminal history.
2. Review final diff against cascade/board/DESIGN.md, cascade/workspace/DESIGN.md, cascade/boss/DESIGN.md and cascade/DESIGN.md. Keep one owner per requirement/decision, source-linked implementation structure, normal/failure/restart sequence, persistence and navigable C4 links; remove delivery-history narration from designs.
3. Reconcile authoritative model.dsl, views.dsl and workspace.contract.json through the revision-pinned workflow. Cover cascade-board-code, cascade-workspace-code, cascade-boss-code and publication consumer nodes with real declaration kinds and sourcePath/sourceSymbol/parent; update affected component relationships. Validate context → container → component → Code, Level up, deep link, source opening, stale symbols, warm-cache reuse and render bounds with measured evidence.
4. Record paths reviewed, diagram-impact inventory by level, checks and unresolved gaps in work closeout. No accepted snapshot rewrite or unsupported claim of verification.

5. Include cascade-teams-code publication caller and cascade-board-code parser alongside Workspace/Boss in the final integrated source contract and C4 review. Compare each Task's changed source to its owning DESIGN.md and the pinned model; trace normal and refusal/restart paths from Code to persistent Git, board and registry state. Record exact navigation/render/source-opening results, measured warm reuse and bounds, and justified unchanged context/container views in the work closeout.

## Files likely touched

tests/test_review_publication_safeguards.py; tests/workspace/test_integration_worktrees.py; tests/workspace/test_branch_synchronization.py; tests/boss/test_merge.py; cascade/board/DESIGN.md; cascade/workspace/DESIGN.md; cascade/boss/DESIGN.md; cascade/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}.

## Implementation notes

Run a real Git journey across clean/invalid exact results, split roots, stacked/squash/rebase histories, cancellation, moved descendants, repeated delivery and target drift. Verify all accepted boards are unique and terminal history is retained. Reconcile Board, Workspace, Boss and package DESIGN.md; update pinned model.dsl, views.dsl and workspace.contract.json via existing workflow. Validate source contract/render and context→container→component→Code navigation, Level up, deep links, source opening, cache reuse and render bounds; record measured evidence and gaps.

## Skills

_(none)_

## Test plan

Run focused real Git journey suites, source-contract validation and local pinned render. Inspect UI navigation and representative pinned source links; measure warm navigation and render bounds. Report exact commands, results and remaining gaps.

## Out of scope

Live forge mutation, dependency installation, accepted snapshot rewrites, and unrelated architecture inventory.
