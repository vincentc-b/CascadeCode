---
id: task_035_002_004
title: Add end-to-end owned review rebase fixtures
tier: task
status: completed
parent: feat_035_002
children: []
depends_on:
- task_035_002_003
owners:
- swe
skills: []
parent_rev: f15627b1a9c50f00153e41c438a26b1a773efad3
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Add end-to-end owned review rebase fixtures

## Parent Feature

[feat_035_002](../../features/2_active/feat_035_002.md)

## Depends on

- task_035_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add repository-backed end-to-end fixtures that exercise (1) a clean owned-source rebase through checks and lease-safe publication and (2) a semantic conflict that demonstrates bounded conflict handling and the required stop or authorized resolution behavior. Assert source/target SHA capture, authorization revalidation, relevant check evidence, unchanged target, same-review source update, explicit lease protection, and preservation of unrelated user work. Keep fixtures deterministic and limited to the feature's required outcomes.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
