---
id: task_034_007_001
title: Pin completed-work and Git/review evidence inventory
tier: task
status: completed
parent: feat_034_007
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 363c682613c6b73cd83a120de0f26af881816164
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Pin completed-work and Git/review evidence inventory

## Parent Feature

[feat_034_007](../../features/2_active/feat_034_007.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Pin an agreed target baseline and enumerate every completed, non-cancelled epic, feature, and task in the lineage plus reachable target commits. Reconcile direct fixes, merges and available squash/rebase provenance; retrieve linked MR/PR descriptions only through authorized forge access. Deduplicate overlapping work-item, commit and review evidence. Persist a reproducible inventory with exact revisions, explicit unavailable/ambiguous/unreachable provenance, and an initial row for every eligible work item and uncovered commit. Keep historical narratives as leads pending current-code checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
