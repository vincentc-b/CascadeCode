---
id: task_034_005_001
title: Route feature comments with durable accountable handoffs
tier: task
status: completed
parent: feat_034_005
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4893e54f0e77ee61538ee00c395d7c6f539f2e27
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route feature comments with durable accountable handoffs

## Parent Feature

[feat_034_005](../../features/2_active/feat_034_005.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement idempotent CommentPosted delivery for active/staffed features to the live Feature Team and backlog/unstaffed features under an active epic to the Epic Team. Persist originating root comment, feature, affected work, receiving owner, delivery purpose/status and event identity. Carry full source thread/anchor context, prevent duplicate team turns on replay, and expose an explicit single Epic escalation path for live teams. Add focused integrated routing/retry checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
