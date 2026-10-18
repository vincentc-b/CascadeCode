---
id: task_014
title: Mint feature and list children
tier: task
status: completed
parent: feat_004
children: []
depends_on:
  - task_012
  - task_013
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-10
---

# Mint feature and list children

## Parent Feature

[feat_004](../../features/3_completed/feat_004_epic_team.md) — Epic Team graph.

## Depends on

- task_012 (Epic graph runtime / invoke_tool)
- task_013 (Epic tool guard and scoped docs)

## Acceptance criteria

- `mint_feature` writes a feature markdown only under `docs/features/1_backlog/`, parent epic, backlog status, required feature headings.
- Epic `children` frontmatter and `## Feature breakdown` body list updated; second mint appends.
- `FeatureMinted` on queue dest `epic_id` with payload `{feature_id, epic_id}`; readable via `read_events`.
- Does not call `dispatch_feature`, `move_doc`, or activate anything; file stays in backlog.
- `list_children` returns feature-tier children in epic order; skips tasks and missing ids.
- `depends_on` copied when ids exist on the board.
- Tools registered at import of `cascade/epic/mint.py`.

## Files likely touched

- `cascade/epic/mint.py`
- `tests/epic/test_mint.py`

## Implementation notes

Use `allocate_id`, `slugify`, `epic_write_doc`, `tool_guard`, `append_event`. Keyword-only `epic_id` and `root` for registry `invoke_tool(**args)`.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_mint.py tests/epic/test_guard.py tests/epic/test_runtime.py -q`

## Out of scope

- `dispatch_feature` and column moves
- Feature/Task LangGraph graphs
- Boss and War Room UI
