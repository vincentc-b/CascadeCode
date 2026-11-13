---
id: task_034_005_005
title: Create separately approved corrective work or visible human blocker
tier: task
status: completed
parent: feat_034_005
children: []
depends_on:
- task_034_005_002
- task_034_005_003
owners:
- swe
skills: []
parent_rev: 87aca2adc4b8a39f924d3bf8ade32a3d84523a73
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Create separately approved corrective work or visible human blocker

## Parent Feature

[feat_034_005](../../features/2_active/feat_034_005.md)

## Depends on

- task_034_005_002
- task_034_005_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Apply Epic disposition for a corrective feature by minting a new backlog feature with explicit dependencies on accepted work and its own revision-bound plan, sign-offs and human approval; prior epic approval must not authorize it. When change cannot safely fit the epic, show an actionable blocker requiring human replacement/replanning decision, with no automatic backlog return or accepted-work reset. Link outcome to originating thread and held work. Add focused lifecycle checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
