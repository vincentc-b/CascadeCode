---
id: task_063
title: init_workspace and cascade init CLI
tier: task
status: completed
parent: feat_014
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-14
updated: 2026-10-14
---

# init_workspace and cascade init CLI

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

_(none)_

## Acceptance criteria

- **`init_workspace(root: Path) -> WorkspaceRoot`** (new module, e.g. `cascade/workspace/init.py` + `cascade/workspace/types.py`):
  - Requires a git repo at `root` (`cascade.board.gitutil.has_git`); otherwise raise a clear error (no agents started).
  - Creates missing board columns: `docs/{epics,features,tasks}/{1_backlog,2_active,3_completed}` (idempotent; do not delete or move existing plans).
  - Writes `cascade.toml` **only when absent**, with `task_parallelism = 4` and `[models]` keys `epic`, `feature`, `task` present with **empty string** values (boot must fail closed via existing `read_models_table` / `resolve_model`; never `auto`, never copy model ids from the CascadeCode tool checkout).
  - Ensures `.cascade/` appears in `.gitignore` when that line is absent (append one line; do not rewrite the whole file).
  - Does **not** start War Room, watchdog, or any graph; does **not** activate an epic or write `CURSOR_API_KEY` anywhere.
  - Returns a `WorkspaceRoot` dataclass matching the feature spec (`path`, `trunk` resolved via shared trunk helper stub or `None` until task_064, `board`, `config`, `runtime` paths).
- **CLI entry point** in `pyproject.toml`:
  - `[project.scripts]` entry `cascade = cascade.cli:main` (or equivalent) with subcommand **`init`** mapping to `init_workspace` and `--root` defaulting to `cwd`.
  - `cascade init` exits 0 on success; non-git root exits non-zero with stderr message.
- **Dogfood safety**: running `init` against the CascadeCode repo when `docs/` and `cascade.toml` already exist is a no-op for those artifacts (columns may be created if missing; existing TOML untouched).
- **Tests** (`tests/workspace/test_init.py`):
  - Fresh temp git repo: after `init_workspace`, all nine column dirs exist; `.gitignore` contains `.cascade/`; new `cascade.toml` has blank model keys and parallelism 4.
  - Second `init_workspace` call does not overwrite an operator-edited `cascade.toml`.
  - Non-git directory raises.
  - Optional: foreign-repo fixture where `root !=` tool checkout proves no model ids from tool `cascade.toml` are copied.

## Files likely touched

- `cascade/workspace/__init__.py`
- `cascade/workspace/init.py`
- `cascade/workspace/types.py` (`WorkspaceRoot`)
- `cascade/cli.py` (argparse: `init`, placeholder for `up` in task_064)
- `pyproject.toml` (`[project.scripts]`)
- `tests/workspace/test_init.py`
- `tests/support.py` (helpers if needed)

## Implementation notes

- Reuse `cascade.board.context.resolve_root` for path normalization.
- Trunk branch naming can delegate to the same logic task_064/task_069 will share (`resolve_product_trunk`); for task_063, returning `trunk=None` or best-effort name without refusing is acceptable if trunk resolution lives in task_064 — document the split in tests.
- **Risk (trunk pointer on activate)**: feat_014 mentions a trunk pointer on an activated epic; epic activation worktree cutting is task_065, not this task. Do not implement activation here.
- **Risk (blank models TOML)**: confirm empty-string values in `[models]` behave as “present but unusable” (ConfigError / ModelConfigError) rather than “missing tier default.”

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/workspace/test_init.py -q`

## Out of scope

- `cascade up`, process lock, War Room, watchdog (task_064)
- Integration worktrees, branch cuts (task_065)
- Copying the `cascade` package into the target repo
- Cloud/remote UI or multi-repo supervisors
