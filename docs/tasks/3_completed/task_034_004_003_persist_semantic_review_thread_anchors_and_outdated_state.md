---
id: task_034_004_003
title: Persist semantic review-thread anchors and outdated state
tier: task
status: completed
parent: feat_034_004
children: []
depends_on:
- task_034_004_001
owners:
- swe
skills: []
parent_rev: 279ad5d6d4b94f34ac42486290689a3884506afd
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist semantic review-thread anchors and outdated state

## Parent Feature

[feat_034_004](../../features/2_active/feat_034_004.md)

## Depends on

- task_034_004_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Reuse the existing review-thread store and authorization model. Add typed anchors for requirement, view, element and relationship with stable semantic ID/key, current/proposed side, source repository and exact revision, distinct from heading slugs. Validate an anchor against the pinned review payload and preserve its original target and diff path after changes. Missing, renamed without reviewed continuity, or revision-mismatched targets become visibly outdated; blocking state survives until an authorized human resolves the thread. Cover all four types, cross-repository revision identity and outdated behavior in API/storage tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
