---
id: task_046_001_003
title: Resolve and compose revision-pinned review state and semantic inventory
tier: task
status: completed
parent: feat_046_001
children: []
depends_on:
- task_046_001_002
owners:
- swe
skills: []
parent_rev: e764058ea543f073d9075970e610792a3063b4c8
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resolve and compose revision-pinned review state and semantic inventory

## Parent Feature

[feat_046_001](../../features/2_active/feat_046_001.md)

## Depends on

- task_046_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build one authorized current-review resolver over existing store/gates and accepted integration lineage, then extend compose_c4_review_payload. Normalize pending, ready, no_diagram_change, empty_baseline, missing_model/review, unsupported_model, render_failed, invalid_artifact, stale_revision, partial_acceptance and unavailable states with actionable reason and pinned provenance. Include full code/document/plan revisions, tuple/unit/baseline, all view keys and changed views, per-side present/absent/removed, validated semantic elements and relationships, per-target added/removed/changed/unchanged, and deterministic zero/one/many labeled drill choices from containment plus explicit view membership. A claimed change with missing evidence must never appear as no change. Keep projection bounded and reusable by later viewer/approval slices.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
