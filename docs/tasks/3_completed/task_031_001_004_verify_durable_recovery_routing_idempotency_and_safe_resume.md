---
id: task_031_001_004
title: Verify durable recovery, routing idempotency, and safe resume
tier: task
status: completed
parent: feat_031_001
children: []
depends_on:
- task_031_001_003
owners:
- swe
skills: []
parent_rev: 06fb458f1bce07a45b24b842e7dd211e5b95b307
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Verify durable recovery, routing idempotency, and safe resume

## Parent Feature

[feat_031_001](../../features/2_active/feat_031_001.md)

## Depends on

- task_031_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add focused high-signal integration tests covering the supported branch/lifecycle action classes, first-failure persistence, restart recovery, exactly-once owning-team investigation routing, repeated retry idempotency, lifecycle-lock resume after safe repair, precise human blockers, and preservation of user files, approvals, and provenance. Reuse lower-level coverage where integration tests already exercise behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
