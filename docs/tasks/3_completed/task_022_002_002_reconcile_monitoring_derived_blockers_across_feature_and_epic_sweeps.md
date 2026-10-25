---
id: task_022_002_002
title: Reconcile monitoring-derived blockers across feature and epic sweeps
tier: task
status: completed
parent: feat_022_002
children: []
depends_on:
- task_022_002_001
owners:
- swe
skills: []
parent_rev: 404fe156773f0a2b39ef5ba640e96d34bc7e25f4
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Reconcile monitoring-derived blockers across feature and epic sweeps

## Parent Feature

[feat_022_002](../../features/2_active/feat_022_002.md)

## Depends on

- task_022_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Wire the direct-report propagation rule into feature- and epic-level monitoring sweeps so task blockage becomes visible through task → feature → epic without introducing a recursive scan. On later sweeps, detect when the originating child condition has cleared and remove only the matching monitoring-derived cause. Preserve manual blockers and causes from sibling children; never resurrect or mutate terminal work. Reuse canonical transitions and optimistic/version checks, and accept already-applied concurrent outcomes as success.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
