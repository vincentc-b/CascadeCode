---
id: task_034_008_002
title: Reconcile replay rows and accepted deltas into scoped design proposals
tier: task
status: completed
parent: feat_034_008
children: []
depends_on:
- task_034_008_001
owners:
- swe
skills: []
parent_rev: da5f0ed8b5bf9806256d93a51478023418c8c660
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reconcile replay rows and accepted deltas into scoped design proposals

## Parent Feature

[feat_034_008](../../features/2_active/feat_034_008.md)

## Depends on

- task_034_008_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
Use the pinned inventory and G's existing replay ledger to give each of the 2,023 original rows and each newly accepted delta exactly one accountable coverage entry. Keep original IDs and many-to-many evidence links. Assign durable, superseded, no-impact or unresolved with row-specific rationale, exact current-code/test revision references, affected requirement/design/model IDs, and materiality for unresolved gaps.

## Scope
Reuse F's scoped replay/reconciliation services and G's ledger rather than creating a second store. Reject missing/duplicate rows, unsupported claims and blanket no-impact labels. Group evidence only while every row remains individually attributable. Stage only affected leaf/root DESIGN and stable-ID C4 changes through owner-scoped amendment paths; retain proposal and source references. Preserve unavailable child/review evidence as gaps. Do not manufacture historical receipts or reset completed A–G work.

## Done when
Coverage accounting balances original rows plus accepted deltas exactly, every disposition is evidence-linked and material gaps are explicit, and scoped design/C4 proposals are ready for exact-revision architecture review. Include meaningful direct non-Cascade fix, MR-described change, overlapping evidence and unavailable provenance checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
