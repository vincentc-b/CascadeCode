---
id: task_021
title: mint_task and TasksMinted queue event
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_018
  - task_019
  - task_020
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# mint_task and TasksMinted queue event

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_018 — feature graph / queue dest
- task_019 — backlog-only task path sandbox
- task_020 — `feature_write_doc` / guard for task file creation

## Acceptance criteria

- `mint_task(title, depends_on=[], skills=[], body_stub, *, feature_id, root) -> WorkId` in `cascade/feature/mint.py`:
  - Allocates task id via `allocate_id("task", board)`; writes `/docs/tasks/1_backlog/{id}_{slug}.md` only.
  - Frontmatter: `parent=feature_id`, `depends_on`, `skills` (in-repo paths or empty), `parent_rev` = current HEAD SHA of parent feature file (`last_commit_touching` or `read_doc` sha), task tier headings stubbed per board contract.
  - Body includes **Depends on** section listing the same task ids as frontmatter.
  - Updates feature `children` in frontmatter and **Task breakdown** body section; commits via `feature_write_doc` on the feature doc.
  - Appends `TasksMinted { feature_id, task_ids: [new_id] }` to the feature graph queue via `append_event`.
  - **Must not** call `dispatch_task` or move the file to `2_active`/`3_completed`.
  - Refuses with clear error if any **open** comment on this feature (from `docs/_comments/{feature_id}.jsonl`) has `author=human`, `state=open`, and `blocking=true`.
  - Invalid or out-of-repo `skills` paths fail closed (no silent drop).
- Registers `mint_task` on `register_feature_tool`.
- `tests/feature/test_mint.py` covers happy path, `depends_on` in body, children update, blocking comment refusal, skills validation, and no dispatch side effects.

## Files likely touched

- `cascade/feature/mint.py`
- `tests/feature/test_mint.py`

## Implementation notes

Reuse patterns from `cascade/epic/mint.py` for id allocation, slug, breakdown append, and event emission. For the blocking gate, scan `docs/_comments/{feature_id}.jsonl` directly (or call a shared helper once task_023 defines it) without requiring full comment tool wiring in this task.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/feature/test_mint.py -q`

## Out of scope

- `record_decision`, comment reply/resolve (tasks task_022, task_023)
- Task dispatch and column moves
- Epic or feature graph runtime changes beyond registering this tool in `load_feature_tools` (task_024 wiring may import mint module)
