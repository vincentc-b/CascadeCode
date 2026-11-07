---
id: task_009_001_003
title: Add focused flex-mode integration coverage
tier: task
status: completed
parent: feat_009_001
children: []
depends_on:
- task_009_001_001
- task_009_001_002
owners:
- swe
skills: []
parent_rev: 1bdc735a48d8356ee7458d67542480515023e3ca
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
---
# Add focused flex-mode integration coverage

## Parent Feature

[feat_009_001](../../features/2_active/feat_009_001.md)

## Depends on

- task_009_001_001
- task_009_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration tests spanning supported-provider default/enabled behavior, explicitly disabled flex, unsupported-provider normalization/rejection, Codex/OpenAI invocation propagation, and legacy briefs with no flex value. Prefer coverage through existing brief-to-provider flows over redundant low-level tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
