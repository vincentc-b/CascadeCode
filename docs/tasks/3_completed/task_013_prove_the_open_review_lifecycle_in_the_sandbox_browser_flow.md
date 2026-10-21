---
id: task_013
title: Prove the open-review lifecycle in the sandbox browser flow
tier: task
status: completed
parent: feat_005
children: []
depends_on:
- task_012
owners:
- swe
skills: []
parent_rev: 995a10ff226d563902216ae0cae065ec48a0c5b0
created: '2026-10-21'
updated: '2026-10-21'
---
# Prove the open-review lifecycle in the sandbox browser flow

## Parent Feature

[feat_005](../../features/2_active/feat_005.md)

## Depends on

- task_012

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend the existing sandbox browser flow to exercise the critical War Room path end to end: create or expose an open review, confirm it appears with correct feature/epic context and a working direct review link, then merge or close it, refresh the view, and confirm it disappears. Cover the user-visible empty/loading/failure behavior only where the existing harness can do so economically; avoid exhaustive browser cases.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
