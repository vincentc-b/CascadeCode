---
id: task_013_001_002
title: Select audit candidates with bounded fair continuation
tier: task
status: completed
parent: feat_013_001
children: []
depends_on:
- task_013_001_001
owners:
- swe
skills: []
parent_rev: e42512edf87a275dc4c15513cf66b40350b9ad28
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Select audit candidates with bounded fair continuation

## Parent Feature

[feat_013_001](../../features/2_active/feat_013_001.md)

## Depends on

- task_013_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Build a read-only candidate inventory for every nonterminal Task, Feature, and Epic; completed work updated within seven days; and unresolved action, review, publication, reconciliation, or cleanup references regardless of age.

## Acceptance
- A persisted continuation cursor fairly resumes incomplete scans across tiers and restarts without repeatedly scanning full completed history.
- Candidate projection uses canonical tracking repository references and registered product worktrees; duplicate references coalesce by typed work ID.
- One pass can be bounded by the coordinator's 100-item/60-second budget without missing older unresolved completed work.
- Missing or unreadable evidence is surfaced as unavailable, never silently healthy.

## Validation
Exercise cursor continuation, old unresolved references, split repositories, and bounded eventual coverage using existing recovery fixtures.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
