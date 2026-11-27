---
id: task_035_002_003
title: Run repository checks and publish with an explicit force-with-lease
tier: task
status: completed
parent: feat_035_002
children: []
depends_on:
- task_035_002_002
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
# Run repository checks and publish with an explicit force-with-lease

## Parent Feature

[feat_035_002](../../features/2_active/feat_035_002.md)

## Depends on

- task_035_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Run the repository-defined checks relevant to the rebased change and capture their results. Re-read the remote source head immediately before publication, then push the same open review source branch only with an explicit --force-with-lease=<source-ref>:<observed-sha>. Stop safely on failed checks, lease races, remote-head changes, or unexpected dirty paths, preserving user work and surfacing actionable evidence.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
