---
id: task_034_004_001
title: Compose pinned paired C4 review data and changed-view inventory
tier: task
status: completed
parent: feat_034_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 7af5d1b0b8c20965850dc92cff4f898d2946a56b
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Compose pinned paired C4 review data and changed-view inventory

## Parent Feature

[feat_034_004](../../features/2_active/feat_034_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build an owner-scoped review payload from Feature B's validated render, semantic hit-target manifest, and diff plus Feature C's exact review-unit tuple. Pair current and proposed artifacts by stable view key/level, label each repository and pinned revision, enumerate every changed view, and expose semantic legend/summary, requirements/decisions, source/model/plan diffs, and explicit first/empty/removed/error states. A missing or ambiguous binding must return a visible error and source diff; never infer a match from labels, order, coordinates, or transient SVG IDs. Add focused API/integration coverage for revision and failure states.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
