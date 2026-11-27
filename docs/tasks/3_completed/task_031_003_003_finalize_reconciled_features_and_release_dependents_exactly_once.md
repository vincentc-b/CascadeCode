---
id: task_031_003_003
title: Finalize reconciled Features and release dependents exactly once
tier: task
status: completed
parent: feat_031_003
children: []
depends_on:
- task_031_003_002
owners:
- swe
skills: []
parent_rev: dbbba3eb5092540d9e3130d9867ce61973abbfdb
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Finalize reconciled Features and release dependents exactly once

## Parent Feature

[feat_031_003](../../features/2_active/feat_031_003.md)

## Depends on

- task_031_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Complete the Feature only after the reconciliation review has delivered its accepted changes to the intended Epic branch. Make reconciliation callbacks, completion, and dependent-eligibility publication idempotent across retries or duplicate events. Add an end-to-end regression reproducing the feat_029_002 race and asserting no premature completion, Epic delivery, one completion transition, and one dependent release.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
