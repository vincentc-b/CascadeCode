---
id: task_001
title: cascade.board types, paths, and exceptions
tier: task
status: completed
parent: feat_001
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# cascade.board types, paths, and exceptions

## Parent Feature

[feat_001](../../features/3_completed/feat_001_board_schema_git.md) — Board, document contract, and git plan store.

`parent_rev`: null until first commit. Honor the locked API in that Feature.

## Depends on

None.

## Acceptance criteria

- Package `cascade.board` exists and imports cleanly.
- `WorkTier`, `WorkStatus`, `Column`, `WorkId`, `WorkMeta`, `WorkDoc`, `BoardIndex` match feat_001's data structures.
- Path helpers:
  - `column_dir(tier, column) -> Path` under `docs/`
  - `status_for_column(column)` and `legal_folder(status)`
  - `parse_work_id(str) -> (tier, n)` / `format_work_id(tier, n)`
  - filename `{id}_{slug}.md`; lookup is by id, not slug
- Exceptions: `BoardError`, `SchemaError`, `NotFound`, `CycleError`, `StatusMismatch`, `GitError`.
- Unit tests for path pairing (ready_to_plan → 1_backlog, blocked → 2_active) and id format (`epic_001`, `feat_012`, `task_003`).

## Files likely touched

- `cascade/__init__.py`
- `cascade/board/__init__.py`
- `cascade/board/types.py`
- `cascade/board/paths.py`
- `tests/board/test_types.py`
- `pyproject.toml` (if missing)

## Implementation notes

Python 3.12+. Use `dataclasses` or pydantic only if it stays a local dependency-free core — prefer stdlib dataclasses. Do not implement parse, validate, or git in this Task.

## Skills

_(none)_

## Test plan

`pytest tests/board/test_types.py`

## Out of scope

- Reading or writing markdown
- git
- watchdog / dispatch
- Comment sidecars
