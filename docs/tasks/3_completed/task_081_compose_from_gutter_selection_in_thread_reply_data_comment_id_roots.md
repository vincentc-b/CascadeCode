---
id: task_081
title: Compose from gutter/selection + in-thread reply + data-comment-id roots
tier: task
status: completed
parent: feat_017
children: []
depends_on:
- task_080
owners:
- swe
skills: []
parent_rev: ab17d9462ce2063c512efb24bc168dd94361772b
created: '2026-10-20'
updated: '2026-10-20'
---
# Compose from gutter/selection + in-thread reply + data-comment-id roots

## Parent Feature

[feat_017](../../features/2_active/feat_017.md)

## Depends on

- task_080

## Acceptance criteria

- The free-text Section input in `#plan-comments` is removed.
- A root comment can be started from a gutter '+' on a block or from a text selection in `#plan-body`.
- POST /api/comment sends line_start/line_end, section (never empty; nearest ##+ heading slug, H1 slug or `general` above the first H2), anchor (selection text or block first ~120 chars), doc_sha (from GET /api/doc/{id}), and blocking (roots only, from the existing checkbox, default unchecked).
- Each open root has an in-thread reply that POSTs doc_id, body, parent only.
- Threads reload after 202 {ok, comment_id}; no kickoff key is expected.
- Each root renders with `data-comment-id="{root id}"`, kept across re-render, without wiping any Resolve control feat_018 mounted. Open vs resolved shown via `.resolved`.
- `#plan-comments` stays the deep-link hash target; Back to War Room is unchanged.
- If section_slug is ported to JS, a shared (heading, slug) fixture matches Python (e.g. `memory-layout`).

## Files likely touched

- `cascade/war_room/static/plan_viewer.js`
- `cascade/war_room/static/plan_viewer.css`
- `cascade/war_room/static/plan_viewer.html`
- `tests/war_room/test_plan_render.mjs`
- `tests/war_room/test_plan_viewer.py` (only if a route assertion is needed)

## Implementation notes

Upgrade `#plan-comments`: remove the free-text Section input. Start a root comment from a gutter '+' on a block or from a text selection in `#plan-body`. POST /api/comment with line_start/line_end, section (feat_016 `cascade.comments.section_slug` of nearest ##+ heading; above first H2 -> H1 slug or `general`; never empty), anchor (selection text or block first ~120 chars), doc_sha (from GET /api/doc/{id}), blocking from existing checkbox (default unchecked, roots only). In-thread reply on each open root: POST with doc_id, body, parent only. Reload threads after 202 {ok, comment_id} (no kickoff key). Render each root with `data-comment-id="{root id}"`, kept across re-render, without wiping any Resolve control feat_018 mounted; show open vs resolved (`.resolved`). `#plan-comments` remains the deep-link hash target; Back to War Room unchanged. If section_slug is ported to JS: add shared (heading, slug) fixture matching Python (no underscores; double-slugify is a no-op e.g. `memory-layout`). Tests: extend existing plan-viewer tests; no mock-heavy JS unit tests. Honors D1, D4, D5, D6, D8.

## Skills

_(none)_

## Test plan

Gate for this task (extend existing plan-viewer tests only; no new mock-heavy JS unit tests):

- `python -m pytest tests/war_room` passes.
- `node tests/war_room/test_plan_render.mjs` passes, extended to cover the compose and reply payloads, `data-comment-id` on roots, and section-slug cases if ported.

The repo-wide suite has 7 unrelated baseline failures that also fail on `feat/feat_017` without this diff: `tests/agent/test_adapter.py` (2), `tests/agent/test_providers.py` (2), and `tests/{epic,feature,task}/test_graph.py` missing_model_id (3). They are not part of this gate. Do not fix or edit them here.

## Out of scope

- Client-side re-anchor and outdated threads (task_082).
- Server-side changes to the comment API.
- Fixing the pre-existing agent/graph test failures.
