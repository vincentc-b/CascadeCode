---
id: task_078
title: POST /api/comment field pass-through + parent-as-reply
tier: task
status: backlog
parent: feat_016
children: []
depends_on:
- task_077
owners:
- swe
skills: []
parent_rev: ddca58f8a69048ff10e27fb9a4df206ac71467b0
created: '2026-10-19'
updated: '2026-10-19'
---
# POST /api/comment field pass-through + parent-as-reply

## Parent Feature

[feat_016](../../features/2_active/feat_016.md)

## Depends on

- task_077

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend _handle_comment for POST /api/comment: accept line_start, line_end, doc_sha, blocks on roots and pass to store.comment(); slugify section via cascade.comments.section_slug before persist (client may send heading or slug).

When `parent` is set: human reply via existing store reply_comment (emits CommentReplied); section/anchor/blocking/line_*/doc_sha/blocks are ignored; section and anchor inherited from parent; 404 if parent missing. No new /api/comment/reply route.

Root: 400 if section empty or line_end < line_start. blocking=true allowed (human-only). Author always human.

Keep existing kickoff_graph_queue_event call (roots and replies) and the not-attached toast; no second helper, no polling. GET /api/comments/{doc_id} keeps 404/400 behavior and returns new fields.

Tests: API tests on the existing War Room server fixture covering root with new fields, reply via parent, missing parent 404, empty section 400, bad line range 400.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
