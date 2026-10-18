---
id: task_072
title: Per-provider defaults and resolve_backend
tier: task
status: completed
parent: feat_015
children: []
depends_on:
  - task_071
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-16
updated: 2026-10-16
---

# Per-provider defaults and resolve_backend

## Parent Feature

[feat_015](../../features/3_completed/feat_015_provider_backends.md) — Provider backends and credentials.

## Depends on

- task_071 — `ProviderId`, `ProviderConfigError`, `parse_provider_id`

## Acceptance criteria

- **`cascade/watchdog/config.py`**:
  - Add `@dataclass(frozen=True) ProvidersConfig`: `default: ProviderId`, `tables: dict[ProviderId, ModelsTable]` where each `ModelsTable` reuses the existing feat_010 shape (`epic`, `feature`, `task`, `boss`, `roles`) for one provider table.
  - Add `read_providers_config(root: Path) -> ProvidersConfig`:
    - **Legacy:** if `[providers]` is **absent**, treat today's `[models]` table as **`cursor`** only and implicit `default = "cursor"` (via existing `read_models_table`).
    - **New shape:** if `[providers]` is present, read `[providers].default` (required non-blank known `ProviderId`) and each `[providers.cursor]`, `[providers.claude]`, `[providers.codex]` subsection with the same tier/roles validation rules as `read_models_table` (non-blank strings, table shapes).
    - **Conflict:** if **both** `[providers]` and `[models]` are present in the same file → raise `ConfigError` (one source of truth).
    - Absent provider subsection on disk is legal (empty `ModelsTable` for that provider); resolution fails closed when that provider is selected.
  - Keep `read_models_table` and `task_parallelism` behavior unchanged for callers that still use legacy path internally; new code should prefer `read_providers_config`.
- **Document frontmatter** (`provider:`):
  - **`cascade/board/types.py`**: add `provider: ProviderId | None = None` on `WorkMeta`.
  - **`cascade/board/parse.py`**: if `provider` key present → non-blank string parsed via `parse_provider_id`; if absent → `None`. Blank string → `SchemaError`.
  - **`cascade/board/validate.py`**: validate `provider` when set is a known id (via parse helper).
  - **`render_doc`**: emit `provider` only when set (same omission rules as `model`).
- **`cascade/watchdog/model_resolve.py`**:
  - Extend signature: `resolve_model(role: RoleId, doc: WorkMeta | None, *, root: Path, provider: ProviderId) -> ResolvedModel`.
  - Model resolution uses **only** that provider's table from `read_providers_config(root).tables[provider]` — same resolution order as task_051 (document-role → document → project-role → project-tier → boss-falls-back-to-epic), but tier defaults come from `[providers.<id>]` not a flat `[models]`.
  - **No inheritance:** resolving for a feature doc must **not** read the parent epic's `provider` or model; only `doc` passed in and the project table for the **resolved** provider apply (feat_010 rule unchanged).
- **New resolver** in `cascade/watchdog/model_resolve.py` (or `cascade/watchdog/backend_resolve.py`):
  - `ProviderSource = Literal["document", "project-default"]`
  - `@dataclass(frozen=True) ResolvedBackend`: `provider: ProviderId`, `provider_source: ProviderSource`, `model: ResolvedModel`
  - `resolve_backend(role: RoleId, doc: WorkMeta | None, *, root: Path) -> ResolvedBackend`:
    1. If `doc is not None` and `doc.provider` is set → use that provider, `provider_source="document"`.
    2. Else `read_providers_config(root).default` → `provider_source="project-default"` (legacy file → implicit cursor).
    3. Call `resolve_model(role, doc, root=root, provider=that_provider)`.
    4. On missing/blank provider default or unconfigured model → raise `ProviderConfigError` or `ModelConfigError` (fail closed; no `auto` injection).
  - Document override does **not** leak to children (resolver only sees the `doc` argument; callers must not pass parent meta).
- **`cascade/watchdog/__init__.py`**: export new types and `resolve_backend`, updated `resolve_model`.
- **Tests**:
  - `tests/watchdog/test_config.py`: both `[providers]` and `[models]` → `ConfigError`; legacy-only `[models]` → `read_providers_config` yields default cursor; valid new shape round-trips.
  - `tests/watchdog/test_model_resolve.py`: extend with `provider=` — same role resolves different ids from `[providers.claude]` vs `[providers.cursor]`; feature doc with own `model` does not use epic parent (existing test style).
  - `tests/watchdog/test_backend_resolve.py` (new): document `provider:` override; project default; missing tier on selected provider → error.

## Files likely touched

- `cascade/watchdog/config.py`
- `cascade/watchdog/model_resolve.py`
- `cascade/watchdog/__init__.py`
- `cascade/board/types.py`
- `cascade/board/parse.py`
- `cascade/board/validate.py`
- `tests/watchdog/test_config.py`
- `tests/watchdog/test_model_resolve.py`
- `tests/watchdog/test_backend_resolve.py` (new)
- `tests/board/test_parse.py` / `tests/board/test_validate.py` (provider frontmatter)

## Implementation notes

Locked contracts from feat_015:

> **Defaults are per provider, not provider-agnostic ids.** … Each provider table has its own epic / feature / task / optional boss / optional roles map.

> **Legacy:** if `[providers]` is absent, today's `[models]` table is the `cursor` table and the default provider is `cursor`. If both `[providers]` and `[models]` are present, that is `ConfigError` — one source of truth.

> ```text
> resolve_backend(role, doc | None, *, root) -> ResolvedBackend
>     1. doc.provider if set          -> provider_source = document
>     2. cascade.toml [providers].default
>        or implicit cursor from legacy [models]
>                                     -> provider_source = project-default
>     3. resolve_model(role, doc, root, provider=that)
>        against that provider's table only
>     else ModelConfigError / ProviderConfigError
> ```

> `provider` must be a known `ProviderId` or validation fails. A blank string is illegal. Omitted means "use the project default provider." The document override does not leak to children.

> **Operators may expect a feature to inherit its epic's provider.** Rejected for the same reason feat_010 rejected model inheritance.

**`init` template change is NOT this task** (task_073 writes the new `[providers]` scaffold).

Planning agents must not use these readers to self-start (DESIGN.md §9.1 / feat_010).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/watchdog/test_config.py tests/watchdog/test_model_resolve.py tests/watchdog/test_backend_resolve.py tests/board/test_parse.py tests/board/test_validate.py -q`

## Out of scope

- `cascade/workspace/init.py` new TOML shape (task_073)
- Credential resolver and `run_role` provider field (task_073)
- Graph boot wiring calling `resolve_backend` (task_073)
- Claude/Codex subprocess adapters (task_074)
- War Room providers API/UI (task_075)
