---
id: task_045_003_001
title: Repair owned-lineage architecture publication and terminal retry
tier: task
status: completed
parent: feat_045_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 7361567c734ef4e4e82f0a48e4c74f18ba3476bf
created: '2026-11-13'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Repair owned-lineage architecture publication and terminal retry

## Parent Feature

[feat_045_003](../../features/2_active/feat_045_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Repair architecture publication and review validation for the exact authorized owning plan/design lineage in epic and feature integration worktrees before trunk integration. Publish an accepted SWE review from the isolated task worktree.

## Implementation
- Reconcile with the owner of the existing uncommitted runtime changes in cascade/workspace/architecture_publication.py and architecture_review.py before editing; preserve their work and avoid a duplicate or overwrite.
- Resolve each plan and design head through registered owning integration/tracking lineage. Keep separate tracking and product revisions in split roots. Preserve repository keys, roles, destinations, generation, ownership, ancestry, revision, and byte-digest validation.
- Stage current committed branch-local artifacts. Reject changed bytes, unrelated or missing commits, stale review units after later plan/design refresh, and stale proposals.
- Provide supported canonical retry for terminal superseded/artifact_changed publications while preserving pinned proposal and failure history. Do not edit publication ledgers manually, relabel repository roles, invent a generation, rewrite main, merge early, or bypass approval.
- Add focused existing-suite regressions for distinct trunk/owned heads, current and changed plan/design bytes, colocated and split roots, review refresh, and terminal retry. Run relevant checks and publish repair review through canonical tools. No dependency installation.

## Current evidence to exercise
Epic 045: architecture-publication-54cb62ce2796bbd3f644a64468202fefb3878d2270cc54ceda336fde1f808c4e succeeded as no_diagram_change for plan 693476beb0accecbcfb4ab1f36ac9f9a4e84fd59/design 0e3b0651d8b5c667649884ffd68da9839789968f, but its review unit architecture-review-55f435ccdcccafdf2ef920a43f19cdcc6ccfd0a64e9f19451f5131068bb13b00 later became stale with artifact_changed. Feature 001 publication architecture-publication-e386befca2918b6723467733c0b9ec8f051fb7222e1f5af38b5472af10e4ba45 pins plan d4c70116ed7d3fa02a4ff6e610a2ba41214156cc and is superseded/artifact_changed, no review unit. The older 8c50299f publication is historical. Use the then-current reviewed plan/design tuple for any runtime retry.

## Completion evidence
Report code/test acceptance and SWE review separately from the later successful canonical architect publication. Operational publication remains a feature-level architect action after accepted repair is integrated.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
