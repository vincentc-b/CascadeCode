---
id: task_038_003_003
title: Add synthetic dependency lifecycle regressions
tier: task
status: completed
parent: feat_038_003
children: []
depends_on:
- task_038_003_001
- task_038_003_002
owners:
- swe
skills: []
parent_rev: dc7bd73f904777a080fed384a7197c74839daac9
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add synthetic dependency lifecycle regressions

## Parent Feature

[feat_038_003](../../features/2_active/feat_038_003.md)

## Depends on

- task_038_003_001
- task_038_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend existing War Room readiness/board/transcript and lifecycle suites with a synthetic epic_034 -> epic_036 fixture: canonical epic_036 completion overrides a stale active copy while epic_034 cannot read epic_036's spec, and planning/action outcomes remain satisfied. Cover completed/unreadable, readable/incomplete, missing dependency, authoritative-source failure, tracking-repository dependency, mid-turn completion, and stale-success refusal at an action boundary. Assert unchanged scoped authorization and review/stacked behavior. Reuse predecessor board fixtures and API-level tests; avoid production board data, private plan content, redundant helper tests, and a new test framework.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
