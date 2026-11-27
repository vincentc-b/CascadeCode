---
id: task_035_002_001
title: Define bounded review-rebase turn inputs and preflight validation
tier: task
status: completed
parent: feat_035_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4d4838deab7bd422a6776d748386ac64b13ff1f1
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Define bounded review-rebase turn inputs and preflight validation

## Parent Feature

[feat_035_002](../../features/2_active/feat_035_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the repository-backed turn contract so it receives only the authorized review/worktree, linked Git metadata, minimal edit/test operations, and push credentials. Record initial worktree state plus source/target remote SHAs, fetch remotes, and revalidate authorization and both heads before any mutation. Fail closed on dirty unrelated paths, missing/mismatched authorization, or changed heads without discarding user work. Add focused coverage for the preflight stop conditions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
