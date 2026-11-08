---
id: task_013_002_005
title: Validate audit lane behavior in an isolated workspace
tier: task
status: backlog
parent: feat_013_002
children: []
depends_on:
- task_013_002_004
owners:
- swe
skills: []
parent_rev: b24c3e628ad37da5e23ffc42c7fff73c4274b65a
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate audit lane behavior in an isolated workspace

## Parent Feature

[feat_013_002](../../features/2_active/feat_013_002.md)

## Depends on

- task_013_002_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Run high-signal integration validation with controllable clocks and real isolated workspace coordination. Cover restart and overdue coalescence, forward/backward clock jumps, jitter bounds, disabled and invalid configuration, manual/duplicate requests, cross-process overlap, >100-item continuation across tiers, and slow/timed-out I/O. Deliberately block ordinary maintenance and prove audit progress; confirm no catch-up storm, receipt watcher side effects, or unrelated delivery stall. Record any accepted limits and the legacy-maintenance convergence behavior in project docs.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
