---
id: task_039_003_003
title: Render dependency review and resume controls in the War Room
tier: task
status: completed
parent: feat_039_003
children: []
depends_on:
- task_039_003_001
- task_039_003_002
owners:
- swe
skills: []
parent_rev: 2a17eb3c70519770930447877fe786aadc95a131
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Render dependency review and resume controls in the War Room

## Parent Feature

[feat_039_003](../../features/2_active/feat_039_003.md)

## Depends on

- task_039_003_001
- task_039_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend existing epic/plan War Room surfaces and planning-readiness controls with the shared dependency projection. Show bootstrap status, actor, environment mismatch, last attempt, failure/output, exact safe next steps, expected verification, cleanup, and full per-entry binding with missing/current/stale approval. Provide separate human bootstrap review, per-entry or independently persisted batch installation approval, and Ping team after completion/resume controls with pending, refusal, and refreshed feedback. Show blocked planning and no-dependency readiness without redesigning unrelated UI. Verify visible browser behavior and safe rendering of command/output text.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
