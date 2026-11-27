---
id: task_034_005_002
title: Triage material change requests and relay Epic decisions
tier: task
status: completed
parent: feat_034_005
children: []
depends_on:
- task_034_005_001
owners:
- swe
skills: []
parent_rev: 87aca2adc4b8a39f924d3bf8ade32a3d84523a73
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Triage material change requests and relay Epic decisions

## Parent Feature

[feat_034_005](../../features/2_active/feat_034_005.md)

## Depends on

- task_034_005_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Classify feature-plan requests for epic constraints, sibling/accepted-work/architecture and sequencing impact. Require Epic impact triage for every material request after any sibling merge, including apparently local active-feature requests. Persist one decision with affected IDs, accepted sibling/baseline evidence and disposition. Record the Epic decision and reply or relay outcome in the originating comment thread without resolving it. Exercise active/backlog and duplicate escalation scenarios.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
