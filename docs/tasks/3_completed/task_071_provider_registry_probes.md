---
id: task_071
title: Provider registry and probes
tier: task
status: completed
parent: feat_015
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-16
updated: 2026-10-16
---

# Provider registry and probes

## Parent Feature

[feat_015](../../features/3_completed/feat_015_provider_backends.md) — Provider backends and credentials.

## Depends on

_(none)_

## Acceptance criteria

- **New module** (suggest `cascade/agent/providers.py`) defining:
  - `ProviderId = Literal["cursor", "claude", "codex"]`
  - `AuthSource = Literal["env", "user-store", "cli-session", "missing"]`
  - `@dataclass(frozen=True) ProviderStatus`: `id: ProviderId`, `installed: bool`, `authenticated: bool`, `auth_source: AuthSource`
  - `ALL_PROVIDER_IDS: tuple[ProviderId, ...]` listing all three ids in stable order (cursor, claude, codex).
- **Typed errors** in `cascade/agent/errors.py` (or colocated with providers):
  - `ProviderConfigError(Exception)` — invalid provider id in config or document validation contexts.
  - `ProviderNotInstalledError(Exception)` — probe says backend unavailable (`not_installed`).
  - `ProviderNotAuthenticatedError(Exception)` — installed but no credential source (`not_authenticated`).
  - These are distinct from `CursorAgentError` (SDK startup) and from `RoleResult`.
- **`probe_provider(id: ProviderId) -> ProviderStatus`** (single provider):
  - **`cursor`**: `installed=True` when `importlib.util.find_spec("cursor_sdk")` succeeds (Cascade is installed with `cursor-sdk`); `installed=False` when import fails. Does **not** attempt network or read secrets.
  - **`claude`**: `installed=True` when `shutil.which("claude")` is non-`None`; else `installed=False`.
  - **`codex`**: `installed=True` when `shutil.which("codex")` is non-`None`; else `installed=False`.
  - Missing binary → `installed=False`. **Never** download, install, or shell out to an installer.
  - For this task only, set `authenticated=False` and `auth_source="missing"` on every probe (credential + CLI-session detection lands in task_073). Callers must not treat probe as auth truth until task_073 extends probes or a separate auth probe helper exists.
- **`probe_providers() -> list[ProviderStatus]`**: returns one status per known `ProviderId`; **no secrets** in any field (no tokens, no env values, no file contents).
- **`parse_provider_id(value: object) -> ProviderId`**: known id only; blank string, unknown string, or wrong type → `ProviderConfigError` with a clear message.
- **`cascade/agent/__init__.py`**: export public types and `probe_providers` / `probe_provider` / `parse_provider_id` as needed by War Room and resolver tasks.
- **Tests** `tests/agent/test_providers.py` (new):
  - `probe_providers()` returns exactly three entries with expected ids.
  - cursor `installed` tracks whether `cursor_sdk` is importable (patch `importlib.util.find_spec` or `sys.modules`).
  - claude/codex `installed` tracks `shutil.which` results (monkeypatch); missing binary → `installed is False`.
  - Response objects contain no attribute that could hold a token (smoke: only the documented fields exist).
  - `parse_provider_id` accepts each legal id; rejects `""`, `"unknown"`, non-string.

## Files likely touched

- `cascade/agent/providers.py` (new)
- `cascade/agent/errors.py`
- `cascade/agent/__init__.py`
- `tests/agent/test_providers.py` (new)
- `pyproject.toml` (no dependency change; `cursor-sdk` already declared)

## Implementation notes

Locked contracts from feat_015 (do not weaken):

> **Do not install CLIs.** Missing `claude` or `codex` is a status of `not_installed`, not an installer prompt. The Cursor SDK remaining a Python dependency is unchanged.

> ```text
> ProviderStatus
>   id: ProviderId
>   installed: bool
>   authenticated: bool
>   auth_source: AuthSource
>   # installed:
>   #   cursor  → cursor-sdk importable (true if Cascade itself is installed)
>   #   claude  → `claude` on PATH
>   #   codex   → `codex` on PATH
> ```

> ```text
> probe_providers() -> [ProviderStatus]
>     no secrets in the result
> ```

This task establishes ids, shapes, PATH/SDK install probes, and typed errors only. Do not read `~/.cascade/credentials`, process env keys, or CLI login state here unless you split a tiny `probe_installation_only` used by task_073 — task_073 owns full `authenticated` / `auth_source` population for API and turn gating.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/agent/test_providers.py -q`

## Out of scope

- `[providers]` TOML reader, legacy `[models]` alias, `resolve_backend` (task_072)
- Credential resolver, user store, CLI-session auth probes (task_073)
- `run_role` dispatch refactor (task_073)
- War Room HTTP routes (task_075)
- Document frontmatter `provider:` (task_072)
