---
id: task_013_003_001
title: Admit Task delivery incidents through guarded audit capabilities
tier: task
status: completed
parent: feat_013_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 74291b9d2785a179b858d884cc2c2a5eb8311d74
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Admit Task delivery incidents through guarded audit capabilities

## Parent Feature

[feat_013_003](../../features/2_active/feat_013_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Connect Task audit classification and incident contracts to the existing supervisor_recover_task_delivery capability for validated delivery missing, stale execution, and delivery reconciliation. Pin authoritative Feature ID and current generation/evidence; recheck lease, owner, gates and capability under the lifecycle lock before any mutation. Keep missing adapters visible for capability re-evaluation. Deterministic repairs must not start an auditor model turn; only bounded diagnosis or an authorized recovery plan may do so. Add focused audit/capability tests for admission and safe refusal.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
