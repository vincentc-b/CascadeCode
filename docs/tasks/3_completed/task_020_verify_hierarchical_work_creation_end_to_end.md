---
id: task_020
title: Verify hierarchical work creation end to end
tier: task
status: completed
parent: feat_009
children: []
depends_on:
- task_019
owners:
- swe
skills: []
parent_rev: 63309caaa5e1f35ef098602dbdbdb3f18f055ddf
created: '2026-10-22'
updated: '2026-10-22'
---
# Verify hierarchical work creation end to end

## Parent Feature

[feat_009](../../features/2_active/feat_009.md)

## Depends on

- task_019

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add economical end-to-end coverage that creates an epic, a child feature, and dependent tasks through supported creation interfaces; verify canonical hierarchy, persistence round-trips, deterministic next-ID allocation, collision rejection, and regression safety for existing non-backlog identifiers. Fix only defects required to satisfy the feature contract.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
