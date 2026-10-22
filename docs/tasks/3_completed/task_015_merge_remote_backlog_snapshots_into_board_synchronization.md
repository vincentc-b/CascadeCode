---
id: task_015
title: Merge remote backlog snapshots into board synchronization
tier: task
status: completed
parent: feat_006
children: []
depends_on:
- task_014
owners:
- swe
skills: []
parent_rev: 943c6f1f0eedd36540fc30c592e51e8131607be9
created: '2026-10-21'
updated: '2026-10-21'
---
# Merge remote backlog snapshots into board synchronization

## Parent Feature

[feat_006](../../features/2_active/feat_006.md)

## Depends on

- task_014

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Make snapshot-only backlog epics visible through the canonical board and existing sync_briefs cadence without allowing remote data to replace live lifecycle state.

## Scope
- Merge snapshot backlog metadata into board reads.
- Give existing local, active, completed, and integration-worktree state precedence for every known work ID.
- Surface and omit/reject conflicts rather than silently replacing state.
- Invalidate or refresh caches so board reads observe a published snapshot within the existing bound.
- Have sync_briefs report exactly newly visible epic IDs and emit each import toast once across repeated refreshes.
- Keep watchdog polling on this synchronization path.

## Verification
Add focused board/synchronization tests for precedence, cache invalidation, diagnostics, newly-visible ID reporting, and repeated-refresh idempotency; retain existing lifecycle and dispatch coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
