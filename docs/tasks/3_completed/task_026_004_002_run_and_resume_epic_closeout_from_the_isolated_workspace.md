---
id: task_026_004_002
title: Run and resume epic closeout from the isolated workspace
tier: task
status: completed
parent: feat_026_004
children: []
depends_on:
- task_026_004_001
owners:
- swe
skills: []
parent_rev: 8afe236aac71e1d61a745c95ea791e4f5cef4658
created: '2026-10-27'
updated: '2026-10-30'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Run and resume epic closeout from the isolated workspace

## Parent Feature

[feat_026_004](../../features/2_active/feat_026_004.md)

## Depends on

- task_026_004_001

## Acceptance criteria

- All trunk-dependent closeout operations run from the verified isolated checkout supplied by task_026_004_001.
- The normal closeout review is reused when present or opened when absent.
- Closeout advances only after the implementation review is merged and the terminal closeout review is satisfied.
- The original persisted close action resumes with existing retry/idempotency semantics.
- Operator-checkout state is neither used as the closeout source nor mutated.

## Files likely touched

Epic-close orchestration and persisted-action/review integration code; exact paths should follow existing ownership boundaries.

## Implementation notes

Wire epic close so all trunk-dependent closeout work uses the isolated verified-trunk checkout. Preserve existing close/retry semantics and never operate on unrelated operator changes.

## Skills

_(none)_

## Test plan

Extend the nearest orchestration-level tests for review reuse/opening, readiness gates, and persisted-action resumption. Leave the full dirty-trunk system scenario to task_026_004_003.

## Out of scope

Changing review policy, redesigning persisted actions, or adding unrelated closeout behavior.
