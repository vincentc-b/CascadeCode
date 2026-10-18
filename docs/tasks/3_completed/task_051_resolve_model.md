---
id: task_051
title: resolve_model pure resolver
tier: task
status: completed
parent: feat_010
children: []
depends_on:
  - task_049
  - task_050
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# resolve_model pure resolver

## Parent Feature

[feat_010](../../features/3_completed/feat_010_model_defaults_and_overrides.md) — Model defaults and overrides.

## Depends on

- task_049 — `read_models_table` / `ModelsTable` from `cascade/watchdog/config.py`
- task_050 — optional `WorkMeta.model` and `WorkMeta.models` on work documents

## Acceptance criteria

- **New module** (e.g. `cascade/watchdog/model_resolve.py` — keep resolver next to config, not under `cascade/agent/`):
  - `ModelSource = Literal["document-role", "document", "project-role", "project-tier", "boss-falls-back-to-epic"]`
  - `@dataclass(frozen=True) ResolvedModel`: `role: RoleId` (from `cascade/agent/types.py`), `model_id: str`, `source: ModelSource`
  - `class ModelConfigError(Exception)`: raised when no step yields a non-blank id (fail closed; no hardcoded product model; do not inject `auto`)
  - `resolve_model(role: RoleId, doc: WorkMeta | None, *, root: Path) -> ResolvedModel` implements **exactly** this order:
    1. `doc.models[role]` when `doc` is not `None` and map contains `role` → `document-role`
    2. `doc.model` when `doc` is not `None` and `model` is set → `document`
    3. `read_models_table(root)` → `[models.roles].<role>` when present → `project-role`
    4. tier default from `[models].<tier>` where tier is `epic` for `epic_manager`/`epic_architect`, `feature` for `feature_lead`/`feature_architect`, `task` for `swe`, `boss` for `boss` → `project-tier`
    5. **Boss only**: when role is `boss` and step 4 did not set `boss` (optional key absent or blank), use `[models].epic` → `boss-falls-back-to-epic`
    6. else `ModelConfigError`
  - Resolver returns a model id string only; it **never** calls `run_role`, the SDK, or feat_009 adapter code.
  - `doc is None` is required for Boss resolution (no document override path).
  - A feature doc’s epic parent model must **not** be consulted; only `doc` passed in and project table apply.
- **`cascade/watchdog/__init__.py`**: export `resolve_model`, `ResolvedModel`, `ModelSource`, `ModelConfigError`.
- **Tests** `tests/watchdog/test_model_resolve.py` (new file, `make_repo` / `add_doc` from `tests/support`):
  - project-tier default for each role with empty frontmatter
  - `document` and `document-role` beat project defaults; per-role map beats single `model`
  - `[models.roles]` beats tier key; boss uses `[models].boss` when set
  - boss with no `boss` key falls back to `[models].epic` with source `boss-falls-back-to-epic`
  - missing tier default with no doc override → `ModelConfigError`
  - `auto` passes through only when configured in TOML or frontmatter
  - absent `[models]` on disk + no doc override → `ModelConfigError` at resolve time (table absent is legal on disk, illegal when resolving)

## Files likely touched

- `cascade/watchdog/model_resolve.py` (new)
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_model_resolve.py` (new)

## Implementation notes

Reuse `read_models_table` from task_049; do not duplicate TOML parsing. Invalid TOML shapes remain `ConfigError` from the reader; unconfigured but valid empty table surfaces as `ModelConfigError` in `resolve_model`. Role-to-tier mapping must match feat_010 tier table. `task_parallelism` stays untouched.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/watchdog/test_model_resolve.py -q`

## Out of scope

- Boot hooks, LangGraph state, War Room HTTP (task_052)
- Prompt formatting and `run_role` / `RoleTurn` (feat_009 path only consumes the returned id)
- Board parse/validate beyond using `WorkMeta` fields from task_050
