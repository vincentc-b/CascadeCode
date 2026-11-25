---
id: task_013_005_005
title: Complete integrated audit acceptance and default-on release evidence
tier: task
status: completed
parent: feat_013_005
children: []
depends_on:
- task_013_005_003
- task_013_005_004
owners:
- swe
skills: []
parent_rev: 99f211e18eb59cbc54f133d1a1dceceaf8c0af6c
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Complete integrated audit acceptance and default-on release evidence

## Parent Feature

[feat_013_005](../../features/2_active/feat_013_005.md)

## Depends on

- task_013_005_003
- task_013_005_004

## Acceptance criteria

1. Map each of the 24 Epic success criteria to exact selected test command, integrated product revision and observed result.
2. Prove omitted configuration defaults to enabled at 30 minutes in new and existing workspaces, independent of ordinary automation and legacy maintenance; explicit disable still allows guarded manual execution.
3. Selected integrated suite covers restart/concurrency, blocked ordinary watchdog I/O, bounded fair scans, healthy silence, fresh gates, dirty worktrees, split repositories and generation retry/cooldown.
4. Remove the temporary opt-in runtime gate only after real Task, Feature and Epic terminal recovery acceptance; rerun final scoped supervised checks on the clean integrated product head.

## Files likely touched

`cascade/watchdog/config.py`, supervisor activation seam, selected `tests/watchdog`, `tests/war_room`, `tests/feature` and release evidence in the feature spec.

## Implementation notes

Run a selected integrated suite and document observed evidence for all 24 epic criteria. Cover concurrent manual/periodic/parent recovery, crash/restart, ordinary watchdog I/O blocked while audits progress, healthy silence, invalid/disabled intervals, bounded fair scans, approval/comment gates, dirty worktrees, split repositories, and precise retry/cooldown. Fix gaps necessary for release; retain default enablement only after required real adapters pass terminal recovery acceptance. Avoid redundant mock-heavy tests and external package/service installation.

## Skills

_(none)_

## Test plan

Run final scoped suite on clean integrated head and record command/revision/result per criterion. Verify no dependency installation and no healthy-run lifecycle, event, chat, model, Git or timestamp writes.

## Out of scope

Analytics, notifications, UI redesign and broad unrelated test expansion.
