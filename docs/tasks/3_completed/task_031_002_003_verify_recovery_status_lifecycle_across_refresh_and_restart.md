---
id: task_031_002_003
title: Verify recovery status lifecycle across refresh and restart
tier: task
status: completed
parent: feat_031_002
children: []
depends_on:
- task_031_002_001
- task_031_002_002
owners:
- swe
skills: []
parent_rev: bbf83628d2ef91fa5d31a87b61e5061eb8111eec
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Verify recovery status lifecycle across refresh and restart

## Parent Feature

[feat_031_002](../../features/2_active/feat_031_002.md)

## Depends on

- task_031_002_001
- task_031_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add economical, high-signal lifecycle coverage for the complete War Room recovery experience.

## Scope

- Exercise first failure, durable queue acknowledgement, investigating, human-blocked, retry/last-attempt update, and resolution.
- Verify refresh and process restart rehydrate the same active incident.
- Verify the affected row contains safe reason, owner, branch/paths, last attempt, and working action/review target.
- Verify duplicate warnings and repeated toasts are suppressed.
- Prefer existing integration/system fixtures over redundant mock-heavy unit coverage.

## Acceptance

- Automated coverage proves exact transition ordering and persistence.
- A blocked incident identifies owner and next step.
- Resolution clears the active warning.
- Repeated reads/events do not create duplicate warning surfaces.
- Any intentionally untested low-value edge case is documented in the task handoff.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
