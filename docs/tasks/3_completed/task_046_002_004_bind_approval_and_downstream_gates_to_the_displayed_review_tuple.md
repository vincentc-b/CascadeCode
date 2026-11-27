---
id: task_046_002_004
title: Bind approval and downstream gates to the displayed review tuple
tier: task
status: completed
parent: feat_046_002
children: []
depends_on:
- task_046_002_002
- task_046_002_003
owners:
- swe
skills: []
parent_rev: c56b95900e11c7c1174d35d7c1af1b8fccec142f
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Bind approval and downstream gates to the displayed review tuple

## Parent Feature

[feat_046_002](../../features/2_active/feat_046_002.md)

## Depends on

- task_046_002_002
- task_046_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Submit the exact plan revision, review-unit ID, tuple digest and accepted-baseline generation shown by the page. Under the existing serialized mutation boundary, recheck those values and authoritative blocking semantic threads before recording approval; reject stale tabs and replacement races. Reuse the same review-context resolver at dispatch, integration, merge and closeout so only affected work is blocked. Preserve partial split acceptance as partial in UI and gates. Cover forged owner/repository/tuple inputs, a local blocking thread with an unrelated feature remaining eligible, resolution subject to other readiness gates, stale approval races and restart persistence with focused HTTP/integration tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
