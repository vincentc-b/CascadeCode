---
id: task_026_003_003
title: Verify recovery feedback and retry scenarios
tier: task
status: completed
parent: feat_026_003
children: []
depends_on:
- task_026_003_001
- task_026_003_002
owners:
- swe
skills: []
parent_rev: 64d993f7144cd20980d08460f76a7bf2fc3174ff
created: '2026-10-26'
updated: '2026-10-27'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Verify recovery feedback and retry scenarios

## Parent Feature

[feat_026_003](../../features/2_active/feat_026_003.md)

## Depends on

- task_026_003_001
- task_026_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add focused integration/system coverage for the feature acceptance criteria, reusing existing test seams where possible rather than duplicating lower-level tests.

Acceptance:
- A transient forge failure displays the specified recovery details and one retry resumes execution.
- A permission refusal displays the correct non-retryable state and exposes no bypass.
- Concurrent retry attempts result in at most one resumed execution and the UI converges on the resulting state.
- Approval and review gates remain distinct from retry.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
