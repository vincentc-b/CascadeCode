---
id: task_051_001_001
title: Derive Feature delivery lifecycle from existing review evidence
tier: task
status: completed
parent: feat_051_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 39f310304155db0ab23629653b611c1337bbcf73
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Derive Feature delivery lifecycle from existing review evidence

## Parent Feature

[feat_051_001](../../features/2_active/feat_051_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope
Implement the additive, read-only Feature delivery projection in cascade/review.py from canonical owner, current review generation, existing repair/obligation evidence and intended-target evidence. Keep the board schema, original review URL, generation history and top-level compatibility projection. No read path polls the forge, writes registry/lifecycle state, opens a PR or admits repair.

## Acceptance criteria
- A completed source document with all children delivered and its original open review projects nonterminal review_pending with owner, URL, generation and next prerequisite; review-disabled/local integration remains supported.
- Distinguish implementation_ready, repair_requested/admitted, repair_in_progress, merge_verification_pending, verified_integrated and explicit supported terminal disposition. Unknown/missing, closed-unmerged and legacy generation-zero evidence stays nonterminal and does not invent accepted heads. Exact current-generation callback/head/ref fencing remains.
- Expose single and bulk view APIs; retain existing feature_review_view(s) compatibility and stable callers. A repeated read has no forge/network or state mutation.
- Add focused tests in tests/feature/test_review_generations.py and relevant review projection tests for open, legacy, stale, closed-unmerged, repaired, missing and integrated evidence. Use temporary Git when target ancestry matters.
- Reconcile cascade/DESIGN.md shared lifecycle and source-linked normal/failure flow, plus model.dsl, views.dsl and workspace.contract.json for changed Boss review Code nodes. Correct semantic IDs, cascade.codeComponent/parent/sourcePath/sourceSymbol and declaration kinds. Validate source contract and local pinned render where available; record actual checks and design paths in closeout. Preserve accepted snapshots.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
