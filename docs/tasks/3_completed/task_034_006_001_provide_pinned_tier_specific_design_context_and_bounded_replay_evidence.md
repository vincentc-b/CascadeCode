---
id: task_034_006_001
title: Provide pinned tier-specific design context and bounded replay evidence
tier: task
status: completed
parent: feat_034_006
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 753eea6d174602eb5d73d887fb6a6afc4cc32000
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Provide pinned tier-specific design context and bounded replay evidence

## Parent Feature

[feat_034_006](../../features/2_active/feat_034_006.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Expose the relevant pinned owned and ancestor DESIGN.md files, source model fragments, and revisions to Epic, Feature, and Task planning context. Add a bounded historical replay reader for completed, non-cancelled work records and associated Git/review evidence. Enforce ownership and explicit evidence scope so teams cannot browse arbitrary other-team plans or repository files. Acceptance: tier-specific context is revision pinned; allowed replay evidence is available; unrelated or cancelled records and cross-owner content are denied. Reuse existing repository/document services.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
