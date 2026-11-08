---
id: task_014_001_002
title: Implement the unified cancellation command contract
tier: task
status: completed
parent: feat_014_001
children: []
depends_on:
- task_014_001_001
owners:
- swe
skills: []
parent_rev: 72e56b3a1a440166537d3ce868251d0a647eba41
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Implement the unified cancellation command contract

## Parent Feature

[feat_014_001](../../features/2_active/feat_014_001.md)

## Depends on

- task_014_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement one cancellation entry point that resolves an epic, feature, or task and applies the same lifecycle rules. Trim and require a non-empty reason; allow cancellation from backlog and active states; reject completed work without mutation; return success without rewriting metadata or re-triggering effects when already cancelled. Persist the cancelled state and metadata atomically before invoking downstream effects/events. Keep tier-specific branching limited to lookup or existing effect integration, not contract semantics. Surface stable validation/transition errors through the existing command/API boundary.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
