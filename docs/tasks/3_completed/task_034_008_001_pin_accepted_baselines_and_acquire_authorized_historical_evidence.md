---
id: task_034_008_001
title: Pin accepted baselines and acquire authorized historical evidence
tier: task
status: completed
parent: feat_034_008
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 0ab95be2859163cc5ec4ad718b17e1872d5b0b68
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Pin accepted baselines and acquire authorized historical evidence

## Parent Feature

[feat_034_008](../../features/2_active/feat_034_008.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
Extend G's existing inventory and handoff adapters with a versioned BaselinePair, OwnerEvidenceHandoff and ReviewEvidence. Pin the accepted Epic target/tracking repositories and revisions independently from G artifact path/revision/hash. Record F and G integration using actual reachable merge/content evidence; enumerate later accepted deltas.

## Evidence boundary
Request the 34 A–F child record revisions and intent/verification excerpts only from authorized feature owners through the Epic handoff. Capture exact source references or null revision, unavailable reason and responsible owner. Retrieve linked MR/PR descriptions and source revisions through existing authorized forge access; retain capture time, content hash, source/head/base/merge revisions where available, linkage to reachable commits, and explicit unavailable fields. Do not infer child revisions from parents or historical review text from current descriptions.

## Done when
A pinned inventory covers every known child/review lead with exact provenance or an explicit unavailable reason; repository/revision/linkage mismatches fail validation; accepted F/G integration and accepted-delta cut are recorded separately from G source pins; existing G artifacts and row IDs are preserved. Report material acquisition prerequisites without treating missing evidence as no-impact.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
