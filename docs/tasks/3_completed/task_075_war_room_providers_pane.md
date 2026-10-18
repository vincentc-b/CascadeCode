---
id: task_075
title: War Room Providers pane and API
tier: task
status: completed
parent: feat_015
children: []
depends_on:
  - task_071
  - task_073
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-16
updated: 2026-10-16
---

# War Room Providers pane and API

## Parent Feature

[feat_015](../../features/3_completed/feat_015_provider_backends.md) — Provider backends and credentials.

## Depends on

- task_071 — `probe_providers`, `ProviderStatus`, `ProviderId`
- task_073 — credential store write/forget, `read_providers_config` default provider, auth-aware probes

## Acceptance criteria

- **HTTP routes** in `cascade/war_room/server.py` (loopback only; same handler style as existing `/api/board` routes):
  - **`GET /api/providers`** → JSON `{ "default": "<ProviderId>", "providers": [ ...ProviderStatus serializable... ] }`
    - `default` from trunk `read_providers_config(root).default`.
    - Each provider entry matches probe fields: `id`, `installed`, `authenticated`, `auth_source`.
    - **Never echo tokens** or env secret values in the response body.
  - **`POST /api/providers/{id}/token`** — JSON body `{ "token": "<string>" }`
    - Valid known `ProviderId` and non-blank `token` → `write_user_store_token`, respond 2xx.
    - Unknown id or blank token → **4xx** with clear error JSON; **never** write under workspace root.
  - **`POST /api/providers/{id}/forget`**
    - Valid id → `forget_user_store_token` for that provider only; 2xx.
    - Does **not** unset process environment variables; does **not** log the CLI out.
    - Unknown id → 4xx.
- **Serialization** (`cascade/war_room/serialize.py` or inline): map `ProviderStatus` and config default to JSON-safe dicts (no `Credential` type in responses).
- **War Room UI** (localhost chrome on existing War Room — not a new origin):
  - **`cascade/war_room/templates/war_room.html`**: add **Providers** pane/section (nav tab or sidebar panel consistent with amendments/chat patterns).
  - **`cascade/war_room/static/war_room.js`**: on load (and after save/forget), `fetch('/api/providers')` and render three providers with:
    - installed / signed-in labels derived from `installed` + `authenticated`
    - auth source display (`env`, `user-store`, `cli-session`, `missing`)
    - password-style **token field + Save** → `POST /api/providers/{id}/token`
    - **Forget** → `POST /api/providers/{id}/forget`
  - **`cascade/war_room/static/war_room.css`**: minimal styling for the pane (match existing War Room tokens).
  - If `installed === false`: show CLI missing copy; **do not** offer install/download buttons.
  - If `auth_source === "cli-session"`: show signed-in via CLI session; **do not** demand a pasted token (field may be disabled or helper text only).
  - Pane does **not** edit `cascade.toml` (no default provider or model editors).
- **Tests** `tests/war_room/test_providers_api.py` (new):
  - GET returns three providers, includes `default`, no `token` key anywhere in JSON.
  - POST token writes under tmp home `~/.cascade/credentials` (monkeypatch `Path.home`), mode 0600; blank token → 4xx; unknown id → 4xx; workspace tree unchanged.
  - POST forget removes user-store entry only; env var left intact (set env in test, forget, assert env still works for resolver).
  - Optional UI smoke: `tests/war_room/test_ui_render.py` or new test asserts Providers markup present in `war_room.html`.

## Files likely touched

- `cascade/war_room/server.py`
- `cascade/war_room/serialize.py`
- `cascade/war_room/templates/war_room.html`
- `cascade/war_room/static/war_room.js`
- `cascade/war_room/static/war_room.css`
- `cascade/agent/credentials.py` (reuse write/forget helpers)
- `cascade/agent/providers.py`
- `cascade/watchdog/config.py` (`read_providers_config` for default)
- `tests/war_room/test_providers_api.py` (new)

## Implementation notes

Locked contracts from feat_015:

> ```text
> GET  /api/providers
>     { default, providers: [ProviderStatus] }
>
> POST /api/providers/{id}/token
>     body { token: str }
>     write user-level store (0600); never the workspace
>     4xx on unknown id or blank token
>
> POST /api/providers/{id}/forget
>     delete that provider's user-store entry only
>     does not unset the process environment
>     does not log the CLI out
> ```

> War Room **Providers** pane (localhost chrome on the existing War Room, not a new origin):
> - Lists the three providers with installed / signed-in / auth source.
> - Token field + save + forget. GET never echoes a token.
> - If `installed` is false, the pane says the CLI is missing and does not offer to install it.
> - If a CLI **login** is already present on the machine, show `auth_source: cli-session` and do not demand a token.
> - Does not edit `cascade.toml`.

> **Login is in-app and user-scoped.** … War Room can store a token under `~/.cascade/credentials` (mode `0600`). … Environment variables still win (CI / headless).

> **A pasted token in the War Room is still a secret.** The pane is localhost-only. … Toasts and GET payloads name sources, never values.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/war_room/test_providers_api.py tests/war_room/test_http_read.py -q`

## Out of scope

- Claude/Codex subprocess adapters (task_074)
- DESIGN.md documentation (task_076)
- Editing `[providers]` or model defaults from the UI
- Remote/hosted UI or multi-user auth
