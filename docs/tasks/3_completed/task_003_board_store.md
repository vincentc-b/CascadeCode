---
id: task_003
title: Board store — write, move, list, pin, git
tier: task
status: completed
parent: feat_001
children: []
depends_on:
  - task_002
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# Board store — write, move, list, pin, git

## Parent Feature

[feat_001](../../features/3_completed/feat_001_board_schema_git.md) — Board, document contract, and git plan store.

## Depends on

- task_002 (`parse_doc`, `validate_doc`)

## Acceptance criteria

- `list_board(root)` scans `docs/{epics,features,tasks}/{1_backlog,2_active,3_completed}` and returns a `BoardIndex`. No durable cache.
- `allocate_id(tier, board)` returns the next unused `NNN` for that prefix; never reuses a number present in `board`.
- `write_doc(doc)` validates, writes the markdown file, `git add` + `git commit` with `docs: {id} {title}`, returns the SHA. If git is not initialized or has no identity, still write the file and raise `GitError` **after** the write *or* succeed with `sha=None` if the repo has no commits yet — pick one and test it; prefer: initialize is **not** this function's job; uncommitted-repo → write file, `sha=None`, no exception (matches feat_001 lock).
- `move_doc(id, dest_column)` renames onto the destination column, sets default status for that column (`backlog`/`active`/`completed`), validates, commits like `write_doc`. Does not implement dispatch law.
- `read_doc(id, rev=None)` reads working tree or `git show rev:path`.
- `pin_parent(child_id, parent_id)` sets `parent_rev` to the last commit SHA of the parent path, or null if none; writes via `write_doc`.
- Tests run in a temp directory with a throwaway git repo **and** a no-git tree.

## Files likely touched

- `cascade/board/store.py`
- `cascade/board/gitutil.py`
- `cascade/board/__init__.py`
- `tests/board/test_store.py`

## Implementation notes

Git via `subprocess` to `git` (no GitPython required). Commits must not touch unrelated files. Do not `git init` the CascadeCode workspace from tests — use `tmp_path`. `move_doc` must be a single logical operation (rename + status + commit); if validate fails, the file must not have moved.

## Skills

_(none)_

## Test plan

`pytest tests/board/test_store.py`

## Out of scope

- `dispatch_task` / authority checks
- Task worktrees (`task/{id}` branches) — feat_007
- Comment JSONL
- Creating commits on the real workspace `main` unless the operator asked
