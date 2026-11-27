---
id: task_031_001_003
title: Implement bounded supervisor repair and same-action resume
tier: task
status: completed
parent: feat_031_001
children: []
depends_on:
- task_031_001_002
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
# Implement bounded supervisor repair and same-action resume

## Parent Feature

[feat_031_001](../../features/2_active/feat_031_001.md)

## Depends on

- task_031_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Provide bounded, explicitly safe supervisor repair operations and a command that resumes the original recorded action rather than creating a replacement. Run resume under the lifecycle lock, enforce valid durable state transitions, retain identity/evidence/provenance, and surface precise human blockers when automated repair cannot proceed.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
