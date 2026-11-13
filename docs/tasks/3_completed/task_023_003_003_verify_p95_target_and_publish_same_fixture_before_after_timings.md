---
id: task_023_003_003
title: Verify p95 target and publish same-fixture before/after timings
tier: task
status: completed
parent: feat_023_003
children: []
depends_on:
- task_023_003_002
owners:
- swe
skills: []
parent_rev: 83fea7a554b33e575ac8982bb848817424605bda
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify p95 target and publish same-fixture before/after timings

## Parent Feature

[feat_023_003](../../features/2_active/feat_023_003.md)

## Depends on

- task_023_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Validate the completed War Room path against the feature performance contract and publish auditable before/after results.

## Scope

- Run at least 20 post-change samples on the exact fixture and measurement boundaries established in task_023_003_001.
- Compute p95 navigation-to-usable-board latency and summarize board API, render, and action-feedback timings.
- Compare before/after results, including run count, environment, and any observed variance.
- Confirm lifecycle freshness and current error behavior remain intact.

## Acceptance criteria

- At least 20 comparable post-change runs are recorded.
- Initial usable-board p95 is under 2 seconds.
- Before/after timings for all four required metrics are published with the shared fixture and method.
- Relevant functional checks pass and freshness/error behavior is explicitly verified.
- If the p95 target is missed, the task reports the measured blocker and evidence rather than presenting the feature as complete.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
