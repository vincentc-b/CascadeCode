---
id: task_034_007_004
title: Validate historical reconstruction and final acceptance
tier: task
status: completed
parent: feat_034_007
children: []
depends_on:
- task_034_007_003
owners:
- swe
skills: []
parent_rev: c57403e2106201d81c35a0c4cf7056f9ea5a23a3
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate historical reconstruction and final acceptance

## Parent Feature

[feat_034_007](../../features/2_active/feat_034_007.md)

## Depends on

- task_034_007_003

## Acceptance criteria

- Recheck the accepted target HEAD and board/tracking revision against the refreshed inventory baseline. Ledger and disposition every newly accepted work item and reachable commit before closure; report any pending Feature F review as pending, not merged evidence.
- Validate directory coverage and owner mapping, root/leaf consistency, cross-directory interfaces, one-home requirement/decision IDs, citations, C4 element/view links, and DESIGN.md TOC headings against current code/tests. Name every material mismatch or unavailable source.
- Process the exact authored DSL bytes with the existing pinned Structurizr image digest; record successful DSL validation, JSON export, and SVG render plus artifact hashes/revisions. Verify the rendered views correspond to the stable model IDs and design references.
- Exercise focused final scenarios for direct fixes, MR-described non-Cascade changes, overlapping work/commit/review evidence, superseded/cancelled plans, and unavailable/ambiguous provenance. Exercise paired review, split acceptance, and living-epic closeout paths without duplicating prior slice test suites.
- Record exact-revision Task/Feature/Epic reconciliation receipts and run the relevant F closeout validators. Deliver a final evidence/gap report that identifies accepted, pending, and unresolved artifacts; clean completion requires no material unresolved gap or pending promotion.

## Files likely touched

- Configured architecture destination: final validation and delta report, model exports, affected DESIGN.md/DSL/mapping corrections.
- Focused final integration checks and reconciliation receipts.

## Implementation notes

Reuse checks from earlier slices where available. Treat the pinned inventory, authorized review bodies, actual code/tests, accepted design revisions and exported model bytes as separate evidence. A passed check does not convert unavailable provenance into known provenance.

## Skills

_(none)_

## Test plan

Run focused final scenario and consistency checks, plus real pinned Structurizr validate/export/render. Capture exact inputs, outputs, digest, revisions and outcomes in the report. Run F closeout validation at the correct gates and expose any pending or failing gate.

## Out of scope

Installing/upgrading Structurizr or changing the approved cross-feature contracts. Raise incompatible contract changes through the amendment path.
