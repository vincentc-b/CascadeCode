---
id: task_082
title: Client-side re-anchor + outdated threads
tier: task
status: completed
parent: feat_017
children: []
depends_on:
- task_081
owners:
- swe
skills: []
parent_rev: ab17d9462ce2063c512efb24bc168dd94361772b
created: '2026-10-20'
updated: '2026-10-20'
---
# Client-side re-anchor + outdated threads

## Parent Feature

[feat_017](../../features/2_active/feat_017.md)

## Depends on

- task_081

## Acceptance criteria

- Placement is client-only. The sidecar is not rewritten.
- If the current doc sha equals a thread's `doc_sha`, the thread is placed at its stored lines.
- If they differ, section threads (section matches a current ##+ heading) search `anchor` within that heading's line range. Doc-level threads (H1/`general`/unmatched section) search `anchor` in the WHOLE body (D7).
- On a hit, the gutter marker moves to the found line. On a miss, the thread is marked outdated and shown at the section heading (or document top if doc-level). It is still blocking if `blocking`.
- The thread list shows the outdated state. The `outdated` set is computed on the client and never persisted.
- `data-comment-id` is kept on re-render.

## Files likely touched

- `cascade/war_room/static/plan_viewer.js`
- `cascade/war_room/static/plan_viewer.css`
- `tests/war_room/test_plan_render.mjs`
- `tests/war_room/test_plan_viewer.py` (only if a route assertion is needed)

## Implementation notes

Client-only placement; do not rewrite the sidecar. When current sha != doc_sha: section threads (section matches a current ##+ heading) search `anchor` within that heading's line range; doc-level threads (H1/`general`/unmatched) search `anchor` in the WHOLE body (D7). Hit -> move gutter marker to the found line; miss -> mark outdated, shown at the section heading (or document top if doc-level), still blocking if `blocking`. If sha matches, place at stored lines. Thread list shows the outdated state; `outdated` set is computed, not persisted. Keep `data-comment-id` on re-render. Test: one fixture covering re-anchor hit and miss for both section and doc-level, added to existing plan-viewer tests. Honors D7.

## Skills

_(none)_

## Test plan

Gate for this task (extend existing tests only, no new mock-heavy JS unit tests):

- `python -m pytest tests/war_room` passes.
- `node tests/war_room/test_plan_render.mjs` passes, extended with one fixture covering re-anchor hit and miss for both section and doc-level threads, plus the sha-match case (stored lines).

The repo-wide suite has 7 unrelated baseline failures that also fail on `feat/feat_017` without this diff: `tests/agent/test_adapter.py` (2), `tests/agent/test_providers.py` (2), and `tests/{epic,feature,task}/test_graph.py` missing_model_id (3). They are not part of this gate. Do not fix or edit them here.

## Out of scope

- Persisting re-anchored positions or the outdated flag.
- Server-side re-anchoring.
- Fixing the pre-existing agent/graph test failures.
