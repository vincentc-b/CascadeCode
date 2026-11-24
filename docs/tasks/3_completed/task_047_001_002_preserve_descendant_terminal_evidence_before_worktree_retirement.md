---
id: task_047_001_002
title: Preserve descendant terminal evidence before worktree retirement
tier: task
status: completed
parent: feat_047_001
children: []
depends_on:
- task_047_001_001
owners:
- swe
skills: []
parent_rev: 7b512001f648eaba8a8ac79170b8f4492a51b9ca
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Preserve descendant terminal evidence before worktree retirement

## Parent Feature

feat_047_001 — descendant-safe retirement. Honor REQ-WORKSPACE-RETIRE-001 and the Epic's persistence success criterion.

## Depends on

- task_047_001_001

## Acceptance criteria

- The retirement proof enumerates every required terminal descendant of a registered parent checkout and checks the authorized destination has its terminal document and delivery/completion provenance. A completed parent copy alone cannot satisfy the proof.
- Missing terminal descendant records are persisted canonically and re-read from the destination before removal. Interrupted persistence or removal retries converge without duplicate terminal records or lost descendants.
- Noncanonical, dirty, locked, occupied or ambiguous checkouts, unmerged source revisions and unresolved review obligations refuse retirement while preserving branch, checkout and registry. A refusal names the missing proof or owner action.
- The Boss caller uses the Workspace proof under the existing lifecycle authority; no second registry or ledger is introduced.
- Update cascade/workspace/DESIGN.md (REQ-WORKSPACE-RETIRE-001), cascade/boss/DESIGN.md (REQ-BOSS-001 caller interface), and cascade/DESIGN.md. Keep source-linked structure, normal/refusal/restart flow and state ownership current.
- Reconcile cascade-supervisor-components, cascade-workspace-code and cascade-boss-code in architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl, views.dsl, workspace.contract.json. Verify sourceSymbol kinds, source-contract validation/render, Context → Containers → Supervisor Components → Workspace/Boss → Code, Level up, deep-link restoration and pinned source. Record specific no-change reasons for landscape/context/container topology.

## Files likely touched

cascade/workspace/integration_worktree.py; cascade/boss/rollup.py; cascade/workspace/DESIGN.md; cascade/boss/DESIGN.md; cascade/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}; focused Workspace/Boss tests.

## Implementation notes

Start with terminal_doc_persisted_outside_worktree, retire_integration_worktree, retire_terminal_registered_worktrees and _retire_feature_worktree. Reuse the exact owner contract from task_047_001_001 and existing board/execution/delivery evidence. Check product versus tracking destinations. Preserve compatibility with existing terminal records and ambiguous legacy data.

## Skills

_(none)_

## Test plan

Use temporary Git repositories and production persistence/removal gates. Cover parent persisted but last completed Task absent, interrupted persistence then restart, split roots, dirty/locked worktree, missing checkout, unmerged source and outstanding review. Run focused Workspace/Boss tests and architecture source validation/render; record command, revision and result.

## Out of scope

General late-repair lifecycle reactivation, forge publication redesign, new registry/ledger.
