---
id: task_026_001_002
title: Implement serialized, bounded, idempotent action resume
tier: task
status: completed
parent: feat_026_001
children: []
depends_on:
- task_026_001_001
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
# Implement serialized, bounded, idempotent action resume

## Parent Feature

[feat_026_001](../../features/2_active/feat_026_001.md)

## Depends on

- task_026_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the durable action record to claim and execute a recoverable lifecycle action exactly once at a time. Route failures by the defined classification, enforce bounded attempts, persist every attempt outcome, and make restart/resume idempotent so repeated or concurrent retry requests cannot emit duplicate downstream team turns, reviews, merges, or completion events. Do not build generic workflow orchestration or presentation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
