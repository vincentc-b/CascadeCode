---
id: task_087
title: HTTP resolve route + Resolve button on plan viewer
tier: task
status: completed
parent: feat_018
children: []
depends_on:
- task_086
owners:
- swe
skills: []
parent_rev: 9d347c8004ae429d56cac63dbc289813b3d1a6e9
created: '2026-10-20'
updated: '2026-10-20'
---
# HTTP resolve route + Resolve button on plan viewer

## Parent Feature

[feat_018](../../features/2_active/feat_018.md)

## Depends on

- task_086

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add POST `/api/comment/resolve` `{doc_id, comment_id}` with author forced to `human`: 202 `{ok, comment_id}`; 404 if comment missing; 400 (`NotARoot`) if `comment_id` is a reply; already-resolved root is idempotent 202. Must not call `kickoff_graph_queue_event` or `kickoff_turn` (D2/dec_011).

Plan viewer: add a **Resolve** control on each open root thread, bound to `#plan-comments [data-comment-id]` where the id is a root with `state=open`. No button on replies or resolved roots. On click, call the route then reload threads; resolved threads stay listed (feat_017 `.resolved` styling). Do not wait for feat_017: if the panel still uses the free-text list, stamp `data-comment-id` on each root; if chrome has shipped, mount the button on the existing node and do NOT rewrite `#plan-comments` innerHTML (dec_014).

Tests: one combined plan-viewer + API test covering resolve happy path (202, thread shows resolved), double-click idempotence, reply -> 400, missing -> 404, and no turn kicked off. Keep it to the minimum that proves the seam.

Acceptance: spec feat_018 Scope/In bullets 1 and 4; D2, D6.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
