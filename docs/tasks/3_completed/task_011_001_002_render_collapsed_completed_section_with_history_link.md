---
id: task_011_001_002
title: Render collapsed completed section with history link
tier: task
status: completed
parent: feat_011_001
children: []
depends_on:
- task_011_001_001
owners:
- swe
skills: []
parent_rev: 8e840776999c1293244bb4d01903a6b3313098fb
created: '2026-10-22'
updated: '2026-10-22'
---
# Render collapsed completed section with history link

## Parent Feature

[feat_011_001](../../features/2_active/feat_011_001.md)

## Depends on

- task_011_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Update the War Room completed-epics section to render collapsed on initial load while preserving a stable bounded row selection across expand/collapse. Show a visible repository link beside the section using the project's established repository metadata and completed-epics path conventions, including when zero completed rows render. When metadata is unavailable, keep the affordance visible but disabled using the application's established unavailable-link behavior; the board must continue rendering.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
