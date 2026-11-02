---
id: task_026_001_003
title: Prove restart and concurrent-retry recovery semantics
tier: task
status: completed
parent: feat_026_001
children: []
depends_on:
- task_026_001_002
owners:
- swe
skills: []
parent_rev: d33b686e923560c006a131f82be564d48dbe2e93
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Prove restart and concurrent-retry recovery semantics

## Parent Feature

[feat_026_001](../../features/2_active/feat_026_001.md)

## Depends on

- task_026_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration tests around one logical lifecycle action. Cover supervisor restart during recovery and concurrent retry requests; verify state and attempt history survive restart, attempt bounds and failure routing hold, resume is idempotent, and no duplicate team turns, reviews, merges, or completion events are produced. Prefer integration coverage over redundant mock-heavy unit tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
