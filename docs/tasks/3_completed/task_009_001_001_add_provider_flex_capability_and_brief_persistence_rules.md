---
id: task_009_001_001
title: Add provider flex capability and brief persistence rules
tier: task
status: completed
parent: feat_009_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e5b0defd474c8aa25b24c5cec5eed4b4b09630f1
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
---
# Add provider flex capability and brief persistence rules

## Parent Feature

[feat_009_001](../../features/2_active/feat_009_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define provider-neutral metadata indicating flex-mode support. Make newly created briefs default flex mode on only for supporting providers, prevent enabled flex from being persisted for unsupported providers, and preserve existing/legacy brief behavior. Scope includes Codex/OpenAI capability advertisement based on whether the installed integration can honor flex.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
