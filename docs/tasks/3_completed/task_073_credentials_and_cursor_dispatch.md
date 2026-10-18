---
id: task_073
title: Credentials and Cursor dispatch behind registry
tier: task
status: completed
parent: feat_015
children: []
depends_on:
  - task_071
  - task_072
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-16
updated: 2026-10-16
---

# Credentials and Cursor dispatch behind registry

## Parent Feature

[feat_015](../../features/3_completed/feat_015_provider_backends.md) — Provider backends and credentials.

## Depends on

- task_071 — `ProviderId`, probes, typed provider errors
- task_072 — `resolve_backend`, extended `resolve_model`, `[providers]` config

## Acceptance criteria

- **Credential types** (suggest `cascade/agent/credentials.py`):
  - `@dataclass(frozen=True) Credential`: `provider: ProviderId`, `token: str` (never logged, never returned by HTTP GET).
  - `resolve_credential(provider: ProviderId) -> Credential | None` with **first match wins**:
    1. Process environment: `CURSOR_API_KEY` (cursor), `ANTHROPIC_API_KEY` (claude), `OPENAI_API_KEY` (codex) — non-blank only.
    2. User-level store `~/.cascade/credentials` (mode **0600** on write; shape is implementation detail).
    3. Existing CLI **login** on this machine (claude/codex only): vendor credential file the CLI already wrote — **not** a running process. **Cursor has no CLI-session source in v1.**
    4. Else `None`.
  - **Never** read `.netrc`, workspace dotenv, `cascade.toml`, Cursor `setting_sources`, or anything under the workspace root for secrets.
- **User store I/O** (same module or `cascade/agent/credential_store.py`):
  - `write_user_store_token(provider: ProviderId, token: str) -> None` — creates `~/.cascade/` if needed, file mode **0600**, never writes under workspace.
  - `forget_user_store_token(provider: ProviderId) -> None` — removes that provider's entry only; idempotent if missing.
  - Helpers used by War Room routes in task_075; expose enough for tests without echoing tokens.
- **Extend probes for auth** (update `probe_provider` / `probe_providers` from task_071):
  - Set `authenticated=True` and correct `auth_source` when `resolve_credential` would succeed (env → `env`, user store → `user-store`, CLI login → `cli-session`).
  - Else `authenticated=False`, `auth_source="missing"`.
  - Still **no secret values** in `ProviderStatus`.
- **`RoleTurn`** (`cascade/agent/types.py`): add required field `provider: ProviderId` (caller-supplied after boot resolution).
- **`run_role`** (`cascade/agent/adapter.py`):
  - Reject blank/whitespace `provider` (via `parse_provider_id` or dedicated validator) and blank `model_id` before dispatch.
  - Reject cloud/remote runtime options (`reject_cloud_runtime` unchanged for Cursor path).
  - Require `probe_provider(turn.provider).installed`; else raise `ProviderNotInstalledError` (not retryable).
  - Require `resolve_credential(turn.provider)`; else raise `ProviderNotAuthenticatedError` (not retryable).
  - **Dispatch `cursor`**: existing async SDK path (`AsyncClient.launch_bridge`, `AsyncAgent.prompt`, dispose before return). Pass credential token as `api_key`; do **not** rely on ambient `CURSOR_API_KEY` alone if resolver returned a user-store token (env still wins in resolver order).
  - **Do not substitute** another provider or model when probe or credential fails.
  - Non-cursor providers: raise a clear typed error (e.g. `ProviderNotImplementedError` or defer to task_074) — must not silently fall back to Cursor.
- **`cascade/workspace/init.py`**: replace default template when creating new `cascade.toml` with feat_015 shape:
  - `[providers] default = "cursor"`
  - `[providers.cursor]`, `[providers.claude]`, `[providers.codex]` each with `epic = ""`, `feature = ""`, `task = ""` (blank keys so boot fails closed until operator fills default provider's models).
  - Do **not** overwrite existing config files.
- **Graph boot / wiring** — call `resolve_backend` and pass provider + model into turns and role prompts (same visibility as feat_010 model source strings):
  - `cascade/epic/boot.py`, `cascade/epic/wiring.py`, `cascade/epic/graph.py` (via `seed_epic_role_models` or successor)
  - `cascade/feature/boot.py`, `cascade/feature/wiring.py`, `cascade/feature/graph.py`
  - `cascade/task/boot.py` / graph paths that seed SWE model
  - `cascade/boss/` model turn entrypoints that today call `resolve_model`
  - `cascade/agent/planning_turn.py`, `cascade/agent/graph_turn.py`, `cascade/task/swe_turn.py`: build `RoleTurn` with `provider` + `model_id`
  - Role prompt text includes resolved **provider id**, **provider_source**, **model_id**, and **model source** (extend existing feat_010 prompt lines).
  - On `ProviderConfigError`, `ModelConfigError`, or `ConfigError` at boot → `toast_model_config_failure` (or generalized toast) and **do not** start the graph / call `run_role`.
- **Tests**:
  - `tests/agent/test_credentials.py` (new): env precedence over user store; user store read/write/forget; cursor never uses cli-session; never reads workspace paths (tmpdir root with fake cascade.toml must not be consulted for secrets).
  - `tests/agent/test_adapter.py`: extend — `RoleTurn` requires `provider`; missing credential → typed error, no SDK call; cursor path still mocked; cloud rejection unchanged.
  - `tests/workspace/test_init.py`: new repos get `[providers]` scaffold with blank tier keys; `resolve_backend` / `resolve_model` fail closed on fresh init.
  - Update graph/wiring tests that patch `resolve_model` to patch `resolve_backend` or supply `provider` on `RoleTurn` (`tests/epic/test_graph.py`, `tests/feature/test_graph.py`, `tests/agent/test_planning_sandbox.py`, `tests/workspace/test_kickoff.py` as needed).

## Files likely touched

- `cascade/agent/credentials.py` (new)
- `cascade/agent/providers.py`
- `cascade/agent/types.py`
- `cascade/agent/adapter.py`
- `cascade/agent/errors.py`
- `cascade/agent/__init__.py`
- `cascade/agent/planning_turn.py`
- `cascade/agent/graph_turn.py`
- `cascade/task/swe_turn.py`
- `cascade/workspace/init.py`
- `cascade/watchdog/model_resolve.py` (imports only if needed)
- `cascade/epic/boot.py`, `cascade/epic/wiring.py`, `cascade/epic/graph.py`
- `cascade/feature/boot.py`, `cascade/feature/wiring.py`, `cascade/feature/graph.py`
- `cascade/task/boot.py`, `cascade/task/graph.py`, `cascade/task/wiring.py`
- `cascade/boss/model_turn.py`, `cascade/boss/graph.py` (if model turns live here)
- `tests/agent/test_credentials.py`, `tests/agent/test_adapter.py`, `tests/workspace/test_init.py`
- `tests/epic/test_graph.py`, `tests/feature/test_graph.py`, `tests/workspace/test_kickoff.py`

## Implementation notes

Locked contracts from feat_015:

> Auth resolution for a turn, first match wins:
> 1. Process environment … (`CURSOR_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).
> 2. User-level store token …
> 3. Existing CLI **login** … Cursor has no CLI-session source in v1 …
> 4. Else fail the turn before launch. Not retryable. Toast names the provider and the missing piece (`not_installed` vs `not_authenticated`).
>
> Do not read `.netrc`, workspace dotenv, Cursor `setting_sources`, or `cascade.toml` for secrets.

> ```text
> run_role(turn: RoleTurn) -> RoleResult
>     reject blank provider or model_id
>     reject cloud / remote runtime options
>     require probe(provider).installed
>     require resolve_credential(provider)
>     dispatch to that backend
>     dispose before return
>     do not substitute a different provider or model
> ```

> `init` writes the new shape: `default = "cursor"` and blank epic/feature/task keys under each of the three provider tables, so boot still fails closed until the operator fills the default provider's models.

> `run_role` remains the only graph entry. Epic, feature, task, and boss boot call `resolve_backend` and put both ids plus their sources in the role prompt (same visibility as feat_010).

**CLI-session probe:** pick one documented check per vendor CLI; if probe output is ambiguous → treat as `not_authenticated`, not a guessed yes (feat_015 risks section). Document the chosen probe in module docstring; task_074 may refine for subprocess launches.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/agent/test_credentials.py tests/agent/test_adapter.py tests/agent/test_providers.py tests/workspace/test_init.py tests/epic/test_graph.py tests/feature/test_graph.py -q`

## Out of scope

- Claude/Codex subprocess `run_role` backends (task_074)
- War Room HTTP + Providers pane UI (task_075)
- DESIGN.md edits (task_076)
- Installing CLIs or cloud agent runtimes
