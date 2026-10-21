---
id: task_012
title: Implement the open merge requests War Room view
tier: task
status: completed
parent: feat_005
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 995a10ff226d563902216ae0cae065ec48a0c5b0
created: '2026-10-21'
updated: '2026-10-21'
---
# Implement the open merge requests War Room view

## Parent Feature

[feat_005](../../features/2_active/feat_005.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build the War Room view against the feat_003 open-reviews endpoint as the sole source of truth. Render each open review with its feature/epic context and a working direct review link. Include usable loading, empty, and failure states, plus refresh behavior that re-queries the authoritative API so merged or closed reviews disappear. Do not add a client-side or secondary persistent store. Add focused implementation-level coverage only where it provides signal beyond the browser flow.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
