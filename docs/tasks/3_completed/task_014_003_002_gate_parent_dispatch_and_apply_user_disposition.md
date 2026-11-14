---
id: task_014_003_002
title: Gate parent dispatch and apply user disposition
tier: task
status: completed
parent: feat_014_003
children: []
depends_on:
- task_014_003_001
owners:
- swe
skills: []
parent_rev: 21f50103ca5a89183a9d580f48160122aec2e029
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Gate parent dispatch and apply user disposition

## Parent Feature

[feat_014_003](../../features/2_active/feat_014_003.md)

## Depends on

- task_014_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

On child cancellation, persist feedback and pause/gate the parent before any further dispatch. Implement the three user choices—continue with reduced scope, replace/replan, or cancel parent—and record the selected disposition in the owning plan/decision trail. Ensure dispatch resumes only when the chosen disposition permits it.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
