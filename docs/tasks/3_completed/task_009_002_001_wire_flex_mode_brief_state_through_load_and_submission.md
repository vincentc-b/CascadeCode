---
id: task_009_002_001
title: Wire flex-mode brief state through load and submission
tier: task
status: completed
parent: feat_009_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: c9596d0da3760eefc9f8ce5d1b237581d5c81b89
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
---
# Wire flex-mode brief state through load and submission

## Parent Feature

[feat_009_002](../../features/2_active/feat_009_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define and implement the brief editor's flex-mode form field using the existing brief field consumed by provider execution. Default it on for new briefs, preserve an explicit saved opt-out when reopening, and normalize/clear an enabled value when the selected provider is not flex-capable. Keep the change scoped to the existing brief persistence/submission path.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
