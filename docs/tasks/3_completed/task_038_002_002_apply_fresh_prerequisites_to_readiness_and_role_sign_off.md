---
id: task_038_002_002
title: Apply fresh prerequisites to readiness and role sign-off
tier: task
status: completed
parent: feat_038_002
children: []
depends_on:
- task_038_002_001
owners:
- swe
skills: []
parent_rev: 1cfec10b6c847fa75f0a1ce75c93352a25a33cb0
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Apply fresh prerequisites to readiness and role sign-off

## Parent Feature

[feat_038_002](../../features/2_active/feat_038_002.md)

## Depends on

- task_038_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Update plan readiness and direct epic/feature role sign-off to check the owning item's prerequisites at action time using the shared lifecycle result. Preserve existing review, role-specific sign-off, plan revision, body-read authorization, and no-dependency behavior. Verify completion during an active planning turn is recognized on refresh and unmet/unavailable transitions refuse sign-off without a new record.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
