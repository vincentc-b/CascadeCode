---
id: task_002
title: parse_doc and validate_doc
tier: task
status: completed
parent: feat_001
children: []
depends_on:
  - task_001
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# parse_doc and validate_doc

## Parent Feature

[feat_001](../../features/3_completed/feat_001_board_schema_git.md) — Board, document contract, and git plan store.

## Depends on

- task_001 (types, paths, exceptions)

## Acceptance criteria

- `parse_doc(path) -> WorkDoc` reads YAML frontmatter + body. `WorkMeta.path` is the file path. Missing/invalid frontmatter raises `SchemaError`.
- `validate_doc(doc, board)`:
  - required heading names per tier (DESIGN.md §4.2–4.4 / feat_001). Do **not** judge prose.
  - feature/task must have `parent`
  - every `depends_on` id exists in `board.by_id`
  - reject cycles in `depends_on` and parent links (`CycleError`)
  - reject status/folder mismatch (`StatusMismatch`)
  - `skills` entries, if any, are relative paths that resolve inside the repo root (`SchemaError` otherwise)
- Tests use fixture markdown under `tests/board/fixtures/` covering happy path, cycle, missing parent, heading miss, blocked-in-backlog mismatch.

## Files likely touched

- `cascade/board/parse.py`
- `cascade/board/validate.py`
- `cascade/board/__init__.py`
- `tests/board/test_parse.py`
- `tests/board/test_validate.py`
- `tests/board/fixtures/*.md`

## Implementation notes

Use `yaml.safe_load` for frontmatter (PyYAML is acceptable). Required headings are the markdown `##` titles listed in DESIGN.md for that tier, including **Skills** on Tasks. `list_board` is not this Task — tests build a `BoardIndex` in memory.

## Skills

_(none)_

## Test plan

`pytest tests/board/test_parse.py tests/board/test_validate.py`

## Out of scope

- `write_doc`, `move_doc`, git commits
- `allocate_id`, `pin_parent`
- Dispatch authority
