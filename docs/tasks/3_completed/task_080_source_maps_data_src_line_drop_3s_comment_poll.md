---
id: task_080
title: Source maps + data-src-line; drop 3s comment poll
tier: task
status: completed
parent: feat_017
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: ab17d9462ce2063c512efb24bc168dd94361772b
created: '2026-10-20'
updated: '2026-10-20'
---
# Source maps + data-src-line; drop 3s comment poll

## Parent Feature

[feat_017](../../features/2_active/feat_017.md)

## Depends on

None.

## Acceptance criteria

- Each rendered block in `#plan-body` carries a 1-based `data-src-line`, computed from markdown token `raw` lengths against the ORIGINAL body (before Mermaid fence replacement). A block after a Mermaid fence reports its true source line.
- Mermaid and markdown rendering behavior is unchanged.
- The 3s `setInterval` comment poll is gone from `plan_viewer.js`. Comments load on page load and after a successful POST only (D2).
- The review panel is hidden for `tier: task` plans (D3).
- No Python markdown dependency is added.

## Files likely touched

- `cascade/war_room/static/plan_viewer.js`
- `cascade/war_room/static/plan_viewer.css`
- `cascade/war_room/templates/plan_viewer.html`
- `tests/war_room/test_plan_render.mjs`
- `tests/war_room/test_plan_viewer.py`

## Implementation notes

Add 1-based `data-src-line` on each rendered block in `plan_viewer.js` using markdown token `raw` lengths mapped against the ORIGINAL body (before Mermaid fence replacement). No Python markdown dependency. Keep Mermaid/markdown rendering behavior. Remove the 3s `setInterval` comment poll; refresh comments only on page load and after a successful POST. Hide the review panel for task plans (feat_016 returns 400). Test: extend existing plan-viewer route+render tests to assert data-src-line present and correct (incl. a doc with a Mermaid fence before later blocks). Honors D2, D3; dec_005 (worktree body/sha).

Status note: commit b56a467 on `task/task_080` already implements this. The earlier `tests_red` came from 7 failures that also fail on the `feat/feat_017` baseline, outside this task's diff: `tests/agent/test_adapter.py` (2), `tests/agent/test_providers.py` (2, credential/auth probes), and `tests/{epic,feature,task}/test_graph.py` missing_model_id (3, `RuntimeError: generator raised StopIteration`). Do not fix or edit those here. On retry, verify the commit and finish without rework.

## Skills

_(none)_

## Test plan

Gate for this task (extend existing tests only, no new mock-heavy JS unit tests):

- `python -m pytest tests/war_room` passes.
- `node tests/war_room/test_plan_render.mjs` passes. It asserts `data-src-line` values, including a Mermaid fence before later blocks.
- The route test asserts no `setInterval` in the served JS and that the task-tier panel is gated.

The repo-wide suite has the unrelated baseline failures listed above. They are not part of this gate.

## Out of scope

- Compose from gutter/selection, reply, `data-comment-id` roots (task_081).
- Re-anchor and outdated threads (task_082).
- Fixing the pre-existing agent/graph test failures.
