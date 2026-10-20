---
id: task_078
title: POST /api/comment field pass-through + parent-as-reply
tier: task
status: active
parent: feat_016
children: []
depends_on:
- task_077
owners:
- swe
skills: []
parent_rev: 6a9092f322a947e128f1ddfd9a643f8e37049273
created: '2026-10-19'
updated: '2026-10-20'
---
# POST /api/comment field pass-through + parent-as-reply

## Parent Feature

[feat_016](../../features/2_active/feat_016.md)

## Depends on

- task_077

## Acceptance criteria

- Root POST `/api/comment` accepts optional `line_start`, `line_end`, `doc_sha`, `blocks` and passes them to `store.comment()`.
- On roots, `section` is slugified with `cascade.comments.section_slug` before persisting (client may send heading or slug).
- Root returns 400 if `section` is empty (after trim) or if both line fields are set and `line_end < line_start`.
- `blocking=true` is allowed on roots; author is always human.
- When `parent` is set, the call is a human reply through the existing `reply_comment` (emits `CommentReplied`). `section`, `anchor`, `blocking`, `line_*`, `doc_sha`, `blocks` are ignored; `section` and `anchor` are inherited from the parent. `section` is not required.
- Missing parent returns 404.
- The existing `kickoff_graph_queue_event` call (roots and replies) and the not-attached toast are unchanged. No second kickoff helper, no polling, no new `/api/comment/reply` route.
- GET `/api/comments/{doc_id}` keeps 404 (unknown id) and 400 (task tier) and returns the new fields.
- The change is real code committed on the task branch. A diff with only markdown is a failure.

## Files likely touched

- `cascade/war_room/server.py` (`_handle_comment`)
- `tests/` War Room server API tests (extend the existing server fixture module)

## Implementation notes

Extend _handle_comment for POST /api/comment: accept line_start, line_end, doc_sha, blocks on roots and pass to store.comment(); slugify section via cascade.comments.section_slug before persist (client may send heading or slug).

When `parent` is set: human reply via existing store reply_comment (emits CommentReplied); section/anchor/blocking/line_*/doc_sha/blocks are ignored; section and anchor inherited from parent; 404 if parent missing. No new /api/comment/reply route.

Root: 400 if section empty or line_end < line_start. blocking=true allowed (human-only). Author always human.

Keep existing kickoff_graph_queue_event call (roots and replies) and the not-attached toast; no second helper, no polling. GET /api/comments/{doc_id} keeps 404/400 behavior and returns new fields.

Import `section_slug` from `cascade.comments` (added by task_077), never from `cascade.board.paths` or `cascade.amendments.store`.

## Skills

_(none)_

## Test plan

API tests on the existing War Room server fixture (no mock-heavy unit tests):

1. Root with `section="Memory layout"`, `line_start=2`, `line_end=4`, `doc_sha`, `blocks=["task_001"]` returns 202; GET shows `section == "memory-layout"` and the new fields.
2. Reply: POST with `parent=<root id>` and no `section` returns 202; GET shows the reply with the parent's `section` and `anchor`, and the other fields ignored.
3. Missing parent returns 404.
4. Root with empty `section` returns 400.
5. Root with `line_start=5`, `line_end=3` returns 400.
6. Assert the kickoff is still called for both a root and a reply, if the fixture already observes it.

Run the War Room server test module and the comments tests and confirm they pass before finishing.

## Out of scope

- A new `/api/comment/reply` route or a second kickoff helper.
- Validating `blocks` ids against the board.
- Resolve HTTP and human-only resolve enforcement (feat_018).
- Viewer UI (feat_017) and gates (feat_019).
- Rewriting historical sidecar sections.
