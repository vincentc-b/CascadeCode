---
id: task_050
title: Model frontmatter on WorkMeta
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

# Model frontmatter on WorkMeta

## Parent Feature

[feat_010](../../features/3_completed/feat_010_model_defaults_and_overrides.md) — Model defaults and overrides.

## Depends on

None (may run in parallel with task_049).

## Acceptance criteria

- **`cascade/board/types.py`**: extend `WorkMeta` with optional document overrides:
  - `model: str | None = None` — single id for every agent on that work object
  - `models: dict[str, str] | None = None` — per-role overrides (only when set in YAML)
  - Neither field is added to `_REQUIRED_KEYS`; omission means “use project default at resolve time,” not an empty string.
- **`cascade/board/parse.py`**:
  - `_meta_from_mapping`: if `model` is present it must be a non-blank string; if absent, leave `WorkMeta.model` as `None`.
  - If `models` is present it must be a YAML mapping with string keys and non-blank string values; wrong shapes raise `SchemaError` at parse time (same style as `_str_list` errors).
  - `render_doc`: include `model` and/or `models` in the YAML payload **only** when set (non-`None`); documents that omit them today must still omit them after `parse_doc` → `render_doc` (no empty-string keys).
- **`cascade/board/validate.py`**: add tier-aware validation (call from `validate_doc` after identity checks):
  - **Epic** legal `models` keys: `epic_manager`, `epic_architect` only
  - **Feature** legal keys: `feature_lead`, `feature_architect` only
  - **Task** legal keys: `swe` only
  - A key from another tier, non-string value, blank string value, or non-mapping `models` → `SchemaError` naming the offending key/field
  - Validate `model` when present is non-blank (parse may already enforce; validate_doc remains the board gate for mint/move)
- **`cascade/board/__init__.py`**: export updated types if public surface changes (only if needed for tests/callers).
- **Tests**:
  - `tests/board/test_parse.py`: round-trip fixture docs with and without `model` / `models`; assert omitted keys stay omitted; assert invalid YAML shapes raise `SchemaError`
  - `tests/board/test_validate.py`: wrong-tier role key in `models` fails validation; happy path with valid overrides on epic/feature/task fixtures (add minimal fixture markdown under `tests/board/fixtures/` if needed)

## Files likely touched

- `cascade/board/types.py`
- `cascade/board/parse.py`
- `cascade/board/validate.py`
- `cascade/board/__init__.py` (if needed)
- `tests/board/test_parse.py`
- `tests/board/test_validate.py`
- `tests/board/fixtures/docs/**/*.md` (optional new fixtures)

## Implementation notes

Document overrides do **not** leak to children: validation only inspects the current doc’s frontmatter. Resolver inheritance order is task_051; this task only persists and validates fields. `depends_on` and dispatch law are unchanged — model frontmatter must not make a document dispatchable.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/board/test_parse.py tests/board/test_validate.py -q`

## Out of scope

- Reading `cascade.toml` `[models]` (task_049)
- `resolve_model` and boot wiring (task_051, task_052)
- War Room or graph runtime behavior
