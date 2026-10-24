---
id: task_006_002_004
title: Prove full-stack default selection end to end
tier: task
status: completed
parent: feat_006_002
children: []
depends_on:
- task_006_002_002
- task_006_002_003
owners:
- swe
skills: []
parent_rev: 40173969c17ff69ea29b07b4ba1aab8b4f3e9137
created: '2026-10-24'
updated: '2026-10-24'
---
# Prove full-stack default selection end to end

## Parent Feature

[feat_006_002](../../features/2_active/feat_006_002.md)

## Depends on

- task_006_002_002
- task_006_002_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add one high-signal end-to-end scenario that discovers available inventory, selects a provider plus epic/feature/task model defaults and a supported reasoning override, creates the brief, reloads or continues the workflow, and verifies the saved values are retained and used downstream. Cover invalid submission behavior within this path where economical; avoid duplicating lower-level validation tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
