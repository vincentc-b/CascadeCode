---
id: task_020
title: Feature scoped read_doc, write_doc, list_children
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_018
  - task_019
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Feature scoped read_doc, write_doc, list_children

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_018 — feature registry for tool registration
- task_019 — `tool_guard` / `FeatureToolDenied`

## Acceptance criteria

- `feature_read_doc(work_id, *, feature_id, root)` in `cascade/feature/scoped_docs.py`:
  - Parent epic: load via `read_doc(epic_id, rev=feature.meta.parent_rev, root=root)` when `parent_rev` is set; include that commit’s body (decision log readable from body). Deny if `parent_rev` is null and policy requires pin (return clear `FeatureToolDenied`).
  - Own feature doc from working tree.
  - Own tasks (`parent == feature_id`) in any task column.
  - Own comments: load lines from `docs/_comments/{feature_id}.jsonl` when `work_id` requests comments or dedicated read path documented in implementation notes.
  - Deny: other features, epic war-room chat, unrelated epics, tasks not owned, other comment sidecars.
- `feature_write_doc(doc, *, feature_id, root)` allows **only** the active feature’s own `.md` (not tasks, not epic); commits via `write_doc`.
- Tool wrappers `read_doc` / `write_doc` in `cascade/feature/docs_tool.py` register on `register_feature_tool`.
- `list_children(*, feature_id, root)` returns `[WorkMeta]` for tasks where `parent == feature_id` (id, title, status, path column inferred); registers as `list_children`.
- `tests/feature/test_scoped_docs.py` covers parent @ `parent_rev`, self write, child task read, denied epic write, denied foreign feature, no war-room transcript reads.

## Files likely touched

- `cascade/feature/scoped_docs.py`
- `cascade/feature/docs_tool.py`
- `tests/feature/test_scoped_docs.py`

## Implementation notes

Mirror `cascade/epic/scoped_docs.py` structure. For comment reads, either accept `work_id == feature_id` with a convention or a helper used by briefing (task_024); do not expose other features’ `_comments` files. `write_doc` must not accept task tier docs. Load feature meta once to obtain `parent` and `parent_rev` for epic reads.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/feature/test_scoped_docs.py tests/feature/test_guard.py -q`

## Out of scope

- `mint_task`, `record_decision` (tasks task_021, task_022)
- Comment append/reply/resolve (task_023)
- Briefing pack assembly (task_024)
- `propose_epic_amendment` (task_025)
