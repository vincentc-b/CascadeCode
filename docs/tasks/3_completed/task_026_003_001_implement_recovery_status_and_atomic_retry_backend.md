---
id: task_026_003_001
title: Implement recovery status and atomic retry backend
tier: task
status: completed
parent: feat_026_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 64d993f7144cd20980d08460f76a7bf2fc3174ff
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Implement recovery status and atomic retry backend

## Parent Feature

[feat_026_003](../../features/2_active/feat_026_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define and expose the recovery status contract for the original War Room action, including phase, typed reason, attempt count, owner, affected checkout or branch, next safe step, and whether the terminal blocker is retryable. Implement a single idempotent/atomic retry operation that resumes at most one execution under concurrent requests. Preserve approval, review, credential, and permission gates; do not create a second orchestration path.

Acceptance:
- Transient forge failures can be marked retryable and resumed through the existing execution path.
- Permission refusals remain non-retryable and cannot bypass permissions.
- Concurrent retry requests produce at most one resumed execution.
- Contract distinguishes retry from approval/review actions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
