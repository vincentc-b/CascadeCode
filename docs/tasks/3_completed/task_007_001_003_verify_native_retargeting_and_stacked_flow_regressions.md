---
id: task_007_001_003
title: Verify native retargeting and stacked-flow regressions
tier: task
status: completed
parent: feat_007_001
children: []
depends_on:
- task_007_001_001
- task_007_001_002
owners:
- swe
skills: []
parent_rev: 1e3c960663ff045315cdec0a9f97f5a001bbece5
created: '2026-10-22'
updated: '2026-10-22'
---
# Verify native retargeting and stacked-flow regressions

## Parent Feature

[feat_007_001](../../features/2_active/feat_007_001.md)

## Depends on

- task_007_001_001
- task_007_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Complete the stacked-PR flow by reconciling downstream pull requests after predecessor merge and validating the integrated behavior.

## Scope
- On reconciliation after the selected predecessor merges, read the downstream PR's actual base.
- Accept the state when GitHub's native retargeting has moved it to the epic's normal integration/base branch.
- If the base is still stale or identity cannot be resolved, expose a clear visible diagnostic and leave the PR unchanged.
- Make reconciliation idempotent across retries and restarts.
- Add high-signal integration coverage spanning room setting, lifecycle, dispatcher, persisted selection, and PR adapter; close only consequential gaps not already covered by predecessor tasks.
- Verify disabling stacked PRs after a stacked PR exists does not rewrite that PR and only changes future eligibility decisions.

## Acceptance
- Native retargeting is verified, not performed.
- Correctly retargeted PRs reconcile successfully.
- Stale bases and missing identity are visible and fail closed.
- Repeated reconciliation creates no duplicate work or PRs.
- Focused regression suite demonstrates the approved feature acceptance criteria without redundant low-level tests.

## Constraints
No explicit provider-side retargeting, merge queue, or broader status/UI redesign.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
