---
id: task_026_003_002
title: Show recovery feedback and safe retry in War Room
tier: task
status: completed
parent: feat_026_003
children: []
depends_on:
- task_026_003_001
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
# Show recovery feedback and safe retry in War Room

## Parent Feature

[feat_026_003](../../features/2_active/feat_026_003.md)

## Depends on

- task_026_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Render recovery phase, typed reason, attempt count, owner, affected checkout or branch, and next safe step on the original War Room action using the backend contract. Show one retry control only for retryable terminal blockers, communicate pending/success/failure state, and prevent duplicate client submissions while a retry is in flight. Keep approval and review controls visually and behaviorally distinct from retry.

Acceptance:
- Users can understand current recovery state and the next safe action without leaving the original action.
- Retry appears only when the backend marks the terminal blocker retryable.
- Permission, approval, review, and credential blockers do not gain a bypass.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
