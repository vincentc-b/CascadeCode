---
id: task_047_001_003
title: Verify owner and retirement convergence across lifecycle surfaces
tier: task
status: completed
parent: feat_047_001
children: []
depends_on:
- task_047_001_002
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
# Verify owner and retirement convergence across lifecycle surfaces

## Parent Feature

feat_047_001 — exact owner and descendant-safe retirement.

## Depends on

- task_047_001_002

## Acceptance criteria

- A production-path regression demonstrates that a completed historical Feature in a sibling checkout cannot authorize mutation over its registered owner's backlog copy; missing/changed ownership refuses safely in colocated and split product/tracking roots.
- A parent terminal copy without its last terminal Task cannot permit retirement. Canonical persistence and removal gates preserve the Task after worktree cleanup, restart and repeated reconciliation, despite a stale active Task checkout.
- Assert the merged board, Task execution ledger, delivery action and parent rollup agree on the terminal Task and its provenance. Exercise normal operations; do not hand-edit success ledgers, fabricate events or bypass gates.
- Review cascade/workspace/DESIGN.md, cascade/boss/DESIGN.md, cascade/board/DESIGN.md and cascade/DESIGN.md against the final diff. Reconcile REQ-WORKSPACE-OWNER-001, REQ-WORKSPACE-RETIRE-001, REQ-BOARD-001 and REQ-BOSS-001 interfaces, source links, execution/failure/restart flow and current evidence; record precise no-change reasons when appropriate.
- Review cascade-supervisor-components, cascade-workspace-code and cascade-boss-code plus model.dsl, views.dsl and workspace.contract.json. Validate source contract/render, code declaration kinds, Context → Containers → Supervisor Components → Workspace/Boss → Code navigation, Level up, deep-link restoration and representative pinned source open. Record grounded no-change reasons for landscape/context/container topology.

## Files likely touched

tests/workspace/test_integration_worktrees.py; tests/boss/test_merge_targets.py or test_rollup.py; tests/war_room/test_resolve_worktree.py; relevant owning DESIGN.md files and architecture source contract if final code requires reconciliation.

## Implementation notes

Build one or two high-signal temporary-repository scenarios around the exact motivating failure and restart. Use normal production persistence, worktree removal and reconciliation operations. Retain accepted review and delivery provenance; report any gap owned by another Feature instead of widening this Task.

## Skills

_(none)_

## Test plan

Run focused Workspace, Boss and War Room tests covering the regressions. Validate C4 source contract and supported render on the final revision; inspect source links, normal and failure paths. Record exact commands/results and any unverified UI navigation limitation in the work record.

## Out of scope

A new late-repair generation protocol, general review workflow changes, full repository suite without a concrete remaining risk.
