---
id: task_037_004_003
title: Show accessible provider diagnostics, remedies and configuration readiness in War Room
tier: task
status: completed
parent: feat_037_004
children: []
depends_on:
- task_037_004_001
- task_037_004_002
owners:
- swe
skills: []
parent_rev: 17dac781a1b3789bee7ff452d6dfbd00b6f91759
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Show accessible provider diagnostics, remedies and configuration readiness in War Room

## Parent Feature

[feat_037_004](../../features/2_active/feat_037_004.md)

## Depends on

- task_037_004_001
- task_037_004_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend the existing provider recovery dialog/panel and board row UI. On failed Epic activation, Feature dispatch, approval-driven dispatch or Task retry, show focused readable diagnostics for all affected roles, selections, safe reasons, document provenance and freshness; explain partial outcomes. Render only server-eligible refresh/retry, provider setup, configuration-change path and Continue without Flex actions through existing review/recovery controls. Show configuration readiness separately from lifecycle/dependency/plan readiness on backlog and active rows, with explicit stale/unknown labels. Refresh dialog and row projections without losing failed-action context; show completion once after idempotent success. Reuse existing keyboard/focus handling and labels, render untrusted text safely, and restore focus on close.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
