---
id: task_049
title: Models config table (cascade.toml)
tier: task
status: completed
parent: feat_010
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Models config table (cascade.toml)

## Parent Feature

[feat_010](../../features/3_completed/feat_010_model_defaults_and_overrides.md) — Model defaults and overrides.

## Depends on

None (may run in parallel with task_050).

## Acceptance criteria

- **`cascade/watchdog/config.py`**: add a typed reader for project model defaults alongside the existing `task_parallelism(root)` implementation (do **not** change `task_parallelism` behavior or signatures).
  - Introduce a small config shape (e.g. frozen dataclass `ModelsTable`) holding optional tier strings: `epic`, `feature`, `task`, `boss`, plus optional per-role overrides from `[models.roles]` (keys are role ids such as `epic_architect`, `feature_lead`, `swe`).
  - Add `read_models_table(root: Path) -> ModelsTable` that reads `cascade.toml` at the repo root with the same file-open / `tomllib` / invalid-TOML handling pattern as `task_parallelism`.
  - **Absent file** or **absent `[models]` table** → return an empty `ModelsTable` (legal on disk; resolver/boot decides when a missing tier default is fatal).
  - **Present `[models]`**: each tier key (`epic`, `feature`, `task`, `boss`) if present must be a non-blank string; blank or non-string → raise `ConfigError` (same family as bad `task_parallelism`).
  - **`[models.roles]`** if present must be a TOML table; a non-table, or any role value that is non-string or blank → `ConfigError`.
  - Top-level frontmatter key `models` on work docs is unrelated; only the TOML table name `[models]` is in scope here.
- **`cascade/watchdog/__init__.py`**: export `read_models_table` and the new type(s) needed by callers; keep exporting `ConfigError`, `task_parallelism` unchanged.
- **Tests** in `tests/watchdog/test_config.py` (extend existing file, same style as `test_parallelism_defaults_and_rejects_non_integers`):
  - missing file / missing `[models]` → empty table
  - valid tier defaults and `[models.roles]` overrides round-trip through the reader
  - non-string tier value, blank tier string, non-table `[models.roles]`, blank role override → `pytest.raises(ConfigError)`
  - malformed TOML → `ConfigError` with decode error context (mirror `task_parallelism` test)

## Files likely touched

- `cascade/watchdog/config.py`
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_config.py`

## Implementation notes

This task reads configuration only; it does **not** call the Cursor SDK and does **not** implement `resolve_model` (task_051). Do not hardcode product model ids. Legal ids include `auto` only when written in TOML. Planning agents must not use this reader to self-start (same constraint as `task_parallelism` in DESIGN.md §9.1).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/watchdog/test_config.py -q`

## Out of scope

- Work document frontmatter `model` / `models` (task_050)
- `resolve_model`, `ModelConfigError`, boot/graph wiring (task_051, task_052)
- Changing dispatch law or `task_parallelism`
