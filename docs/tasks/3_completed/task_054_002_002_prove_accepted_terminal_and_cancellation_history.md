---
id: task_054_002_002
title: Prove accepted terminal and cancellation history
tier: task
status: completed
parent: feat_054_002
children: []
depends_on:
- task_054_002_001
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
# Prove accepted terminal and cancellation history

## Parent Feature

[feat_054_002](../../features/2_active/feat_054_002.md)

## Depends on

- task_054_002_001

## Acceptance criteria

1. Compare the exact candidate tree and pinned accepted target using task 001's physical inventory and existing terminal provenance. Reject missing retained specs, terminal descendant records, reopened copies, changed cancellation reason/timestamp/cleanup outcome, or mismatched accepted parent feedback/disposition.
2. Permit documented lifecycle moves and managed activation pointers without byte equality across valid transitions. Preserve unrelated specs; use resolve_mutation_owner for canonical ownership and fail as unavailable when split-root evidence is absent.
3. Refusals name each affected ID, paths, source/target or accepted revisions, canonical owner, and supported repair prerequisite. Cleanup is previewed through the owner path and repaired candidates are independently validated. Missing or stale proof cannot be reused after target movement.
4. Update cascade/workspace/DESIGN.md terminal history and restart flow, cascade/DESIGN.md publication linkage, and relevant cascade-workspace-code and cascade-teams-code source nodes/contracts; record concrete unchanged context/container/component levels.

5. Validate the changed native cascade-workspace-code and cascade-teams-code nodes in the revision-pinned model, views and source contract: cascade.codeComponent, cascade.parent/sourcePath/sourceSymbol and declaration kind must match real symbols. Run source-contract validation and a pinned local render; traverse context → containers → components → Code, Level up, deep link and pinned source opening for representative nodes, check stale symbols, and record measured warm reuse and render bounds. Trace normal proof and unavailable/target-drift restart against source; record reviewed designs, all-level impact and gaps in closeout.

## Files likely touched

cascade/review_validation.py; cascade/workspace/integration_worktree.py; cascade/workspace/DESIGN.md; cascade/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}; tests/test_review_publication_safeguards.py; tests/workspace/test_integration_worktrees.py.

## Implementation notes

Compare exact candidate/result and pinned accepted target history using the physical scanner and existing terminal provenance. Preserve retained specs, descendant terminal records and exact cancellation fields/parent feedback; allow managed lifecycle pointers. Return exact IDs, paths, revisions, canonical owner and owner-action prerequisite on missing or conflicting evidence. Cover split roots, target movement and replay in real Git tests; reconcile Workspace and Teams Code views.

## Skills

_(none)_

## Test plan

Use real temporary Git repositories for retained and cancelled history, split roots, moved records, managed pointers, target drift and replay. Run focused publication/workspace suites plus architecture source-contract and pinned render checks for changed nodes.

## Out of scope

Merge acceptance wiring, checkout registration, and deleting conflicting copies.
