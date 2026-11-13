---
id: task_045_001_004
title: Repair GitHub review-health snapshot field
tier: task
status: completed
parent: feat_045_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 967e4afcaed5db9f8429aeca080ff93fefe877f3
created: '2026-11-13'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Repair GitHub review-health snapshot field

## Parent Feature

[feat_045_001](../../features/2_active/feat_045_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Review-health recovery for feat_045_001 cannot inspect PR #236 because cascade/tracking.py merge_request_snapshot asks gh pr view --json for unsupported headRefOid. Replace that field with a supported field or remove it if unused. Keep review state, mergeability and comments behavior; add a focused regression that exercises the GitHub CLI field list and confirms an open mergeable PR reaches the healthy path. Validate with the relevant tracking/review-health tests. Scope is the shared snapshot adapter only; do not alter feature readiness or publication lineage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
