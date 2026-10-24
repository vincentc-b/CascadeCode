---
id: task_006_002_003
title: Apply saved model and reasoning defaults to spawned work
tier: task
status: completed
parent: feat_006_002
children: []
depends_on:
- task_006_002_001
owners:
- swe
skills: []
parent_rev: 40173969c17ff69ea29b07b4ba1aab8b4f3e9137
created: '2026-10-24'
updated: '2026-10-24'
---
# Apply saved model and reasoning defaults to spawned work

## Parent Feature

[feat_006_002](../../features/2_active/feat_006_002.md)

## Depends on

- task_006_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Wire the persisted brief defaults into downstream epic, feature, and task creation/execution so each agent layer receives its selected provider, model, and optional reasoning override. Ensure reload and workflow continuation retain the saved configuration, while an omitted/default reasoning choice preserves provider-default behavior. Add focused integration coverage at the handoff boundaries.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
