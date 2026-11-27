---
id: task_031_002_002
title: Render actionable recovery guidance on the affected War Room row
tier: task
status: completed
parent: feat_031_002
children: []
depends_on:
- task_031_002_001
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
# Render actionable recovery guidance on the affected War Room row

## Parent Feature

[feat_031_002](../../features/2_active/feat_031_002.md)

## Depends on

- task_031_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Present the canonical recovery incident as one durable, actionable status on the affected War Room row.

## Scope

- Consume the recovery-state API/board projection without deriving competing client-only state.
- Render failure-specific copy, owner, safe reason, affected branch or paths, last attempt, and the provided action/review link.
- Match the exact queued, investigating, blocked, and resolved transition semantics.
- Suppress duplicate row warnings and repeated toasts for the same incident/transition.
- Ensure resolved incidents remove the active warning.

## Acceptance

- Refresh shows the same active status without duplicating warnings or toasts.
- Blocked incidents visibly name the responsible owner and next step.
- “Investigating” appears only for the durably queued state supplied by the backend.
- Action/review links target the supplied incident destination.
- Resolution clears the row warning.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
