---
id: task_038_002_003
title: Guard direct and bulk plan approval with owning prerequisites
tier: task
status: completed
parent: feat_038_002
children: []
depends_on:
- task_038_002_001
owners:
- swe
skills: []
parent_rev: 1cfec10b6c847fa75f0a1ce75c93352a25a33cb0
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Guard direct and bulk plan approval with owning prerequisites

## Parent Feature

[feat_038_002](../../features/2_active/feat_038_002.md)

## Depends on

- task_038_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Check the current owning epic prerequisites before any bulk approval of backlog children; refuse unmet/unavailable epic prerequisites before writing any child approval. Allow valid unfinished sibling predecessors during bulk plan approval, without treating approval records as execution readiness. Check direct feature approval against that feature's prerequisites. Preserve existing non-dependency approval policy, revision, review, and stacked restrictions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
