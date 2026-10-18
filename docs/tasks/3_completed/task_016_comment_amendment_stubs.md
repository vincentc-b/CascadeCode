---
id: task_016
title: Comment and amendment Epic tool stubs
tier: task
status: completed
parent: feat_004
children: []
depends_on:
  - task_012
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-10
---

# Comment and amendment Epic tool stubs

## Parent Feature

[feat_004](../../features/3_completed/feat_004_epic_team.md) — Epic Team graph.

## Depends on

- task_012 (Epic graph runtime and `register_epic_tool` registry)

## Acceptance criteria

- `EpicToolUnavailable` in `cascade/epic/stubs.py` with `status_code = 501`.
- `reply_comment`, `resolve_comment`, and `resolve_amendment` match the Epic tool signatures; each raises `EpicToolUnavailable` and does not create files under `docs/_comments`, `docs/epics`, or `_amendments`.
- Error messages for comment tools reference **feat_005**; `resolve_amendment` references **feat_006**.
- `decision` on `resolve_amendment` is accepted (`accept` / `reject` / `revise`) but not validated or persisted.
- On import, stubs register with `register_epic_tool` for all three tool names.
- `tests/epic/test_stubs.py` covers 501 behavior, message text, no sidecar dirs, and registry wiring.

## Files likely touched

- `cascade/epic/stubs.py`
- `tests/epic/test_stubs.py`
- `docs/tasks/3_completed/task_016_comment_amendment_stubs.md`

## Implementation notes

Comment storage and epic thread persistence land in feat_005; amendment sidecar format and accept/reject/revise logic land in feat_006. Stubs must not invent sidecar layouts or write diffs. Import `cascade.epic.stubs` from Epic wiring tasks when tools should appear in `epic_tools()`; this task does not modify `cascade/epic/__init__.py`.

## Skills

_(none)_

## Test plan

- `python3 -m pytest tests/epic/test_stubs.py -q`

## Out of scope

- Real comment store, amendment sidecars, or LangGraph invoke wiring changes
- `mint_feature`, `record_decision`, `tool_guard`, package exports
- Edits to feat_004, epic_001, pyproject.toml, graph.py, or guard.py
