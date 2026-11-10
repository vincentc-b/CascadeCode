---
id: task_034_003_003
title: Invalidate review when pinned artifacts or baseline change
tier: task
status: completed
parent: feat_034_003
children: []
depends_on:
- task_034_003_001
- task_034_003_002
owners:
- swe
skills: []
parent_rev: 37a365b227ed51c9ab6f3e7792e5e547dfc6d8e0
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Invalidate review when pinned artifacts or baseline change

## Parent Feature

[feat_034_003](../../features/2_active/feat_034_003.md)

## Depends on

- task_034_003_001
- task_034_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Bind sign-offs and human approval to the exact review-unit tuple. Detect mutation of each reviewed plan, design, model, and source-closure artifact; retain prior evidence while marking affected review invalidated. Detect stale accepted baselines and require rebase/re-review; revalidation alone cannot renew human review. Respect blocking review threads and scoped affected work. Add high-signal checks for each artifact type, destination change, and stale baseline.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
