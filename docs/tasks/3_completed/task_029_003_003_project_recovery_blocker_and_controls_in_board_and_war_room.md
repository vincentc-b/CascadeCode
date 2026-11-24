---
id: task_029_003_003
title: Project recovery blocker and controls in board and War Room
tier: task
status: completed
parent: feat_029_003
children: []
depends_on:
- task_029_003_001
- task_029_003_002
owners:
- swe
skills: []
parent_rev: 31a057bd72ca28ae3eea210198f03e6ab6167319
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Project recovery blocker and controls in board and War Room

## Parent Feature

[feat_029_003](../../features/2_active/feat_029_003.md)

## Depends on

- task_029_003_001
- task_029_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Make provider recovery understandable and actionable in both the board and War Room.

## Scope
- Display the durable blocker and safe reason consistently.
- Show only eligible human actions: Change provider, Retry, provider setup, and Return to backlog.
- Keep provider setup visually and behaviorally distinct from Return to backlog.
- Refresh state safely after an action and communicate refusals without leaking sensitive provider details.

## Acceptance criteria
- Board and War Room agree on blocker reason and available actions.
- Controls are hidden or disabled for ineligible/non-human contexts.
- Active Epic, Feature, clean Task, and dirty Task states render correctly.
- Focused browser/component coverage validates visibility, action dispatch, and error feedback.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
