---
id: task_009_002_002
title: Add capability-gated flex-mode control to brief editor
tier: task
status: completed
parent: feat_009_002
children: []
depends_on:
- task_009_002_001
owners:
- swe
skills: []
parent_rev: 5304ce52a61bad1ddab11ef34768677ae0b0a422
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
---
# Add capability-gated flex-mode control to brief editor

## Parent Feature

[feat_009_002](../../features/2_active/feat_009_002.md)

## Depends on

- task_009_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Render a flex-mode checkbox for flex-capable Codex/OpenAI provider selections, bound to the normalized form field. Hide it for unsupported providers and ensure provider switching follows the normalization behavior established in the data-flow task. Verify the default-on state for a new brief and allow explicit opt-out.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
