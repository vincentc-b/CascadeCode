---
id: task_047_001_001
title: Resolve exact work owner for lifecycle mutation
tier: task
status: completed
parent: feat_047_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: b145775996a2fcf01bd78b886b78efe9e00b5827
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resolve exact work owner for lifecycle mutation

## Parent Feature

[feat_047_001](../../features/2_active/feat_047_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement an explicit mutation-owner resolver using work ID, tier, parent, registered checkout identity, branch, and canonical product/tracking provenance. Keep merged_board and _meta_preference as read projections only. Reject missing/conflicting owners with an actionable typed error; never select a sibling completed copy because it ranks higher. Cover colocated and split roots, returned/backlog snapshots, changed registry or branch, and active/backlog/completed copies. Integrate the resolver at mutation call sites including cascade/workspace/doc_root.py::resolve_doc_worktree only where mutations rely on it; preserve read-only View plan semantics. Update cascade/workspace/DESIGN.md, cascade/board/DESIGN.md interface summary and cascade/DESIGN.md; reconcile cascade-supervisor-components and cascade-workspace-code in model.dsl, views.dsl, workspace.contract.json. Source symbols: resolve_doc_worktree, doc_filesystem_root, merged_board, _meta_preference, get_integration_worktree, and the new resolver. Validate source contract and local render; trace normal owner selection and ambiguity refusal, source deep link and Level up. Focused tests in tests/workspace/test_integration_worktrees.py and tests/war_room/test_resolve_worktree.py using temporary Git repositories. No new registry or broad board ranking rewrite.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
