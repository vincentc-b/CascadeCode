---
id: task_015
title: Epic record_decision tool
tier: task
status: completed
parent: feat_004
children: []
depends_on:
  - task_013
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-10
---

# Epic record_decision tool

## Parent Feature

[feat_004](../../features/3_completed/feat_004_epic_team.md) — Epic Team graph.

## Depends on

- task_013 (Epic tool guard and scoped docs)

## Acceptance criteria

- `record_decision(section, choice, rationale, honors, *, epic_id, root, author=...)` appends a formatted bullet to the Epic `## Decision log` and writes via `epic_write_doc`.
- Decision ids are `dec_NNN` (three digits), monotonic within the log section.
- Missing `## Decision log` raises `ValueError` with a clear message.
- `author` `epic_architect` / `epic_manager` render as Epic Architect / Epic Manager; other values pass through.
- Amendment log and other sections are unchanged; no queue events; no feature file writes.
- Tool registers as `record_decision` on import.

## Files likely touched

- `cascade/epic/decisions.py`
- `tests/epic/test_decisions.py`

## Implementation notes

Load the epic with `epic_read_doc`; scan the decision log slice for `dec_\d{3}`; insert before the next `##` heading or EOF. Date is `date.today().isoformat()`. Do not change status or move columns.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_decisions.py tests/epic/test_guard.py -q`

## Out of scope

- Package exports in `cascade/epic/__init__.py`
- Feature-level decision logs
- Comment store and amendments sidecar
