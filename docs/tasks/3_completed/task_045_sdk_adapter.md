---
id: task_045
title: SDK adapter (run_role)
tier: task
status: completed
parent: feat_009
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# SDK adapter (run_role)

## Parent Feature

[feat_009](../../features/3_completed/feat_009_cursor_agent_backend.md) — Cursor agent backend.

## Depends on

_(none)_

## Acceptance criteria

- New module (suggest `cascade/agent/adapter.py` plus shared types, e.g. `cascade/agent/types.py`) exposing async `run_role(turn: RoleTurn) -> RoleResult`.
- Types:
  - `RoleId`: `epic_manager` | `epic_architect` | `feature_lead` | `feature_architect` | `swe` | `boss`.
  - `RoleTurn`: `role`, `model_id` (required non-blank), `prompt`, `cwd` (`pathlib.Path`), `tools` (MCP server config list for this turn only; shape may be filled by task_046 — adapter passes through unchanged).
  - `RoleResult`: `text`, `status` (`finished` | `error`), `tool_effects` (Cascade-applied effects only; may be empty in this task).
- Validation before any SDK call: missing, blank, or whitespace-only `model_id` raises a clear validation error (not `RoleResult`, not SDK).
- **Local runtime only**: build options with `LocalAgentOptions(cwd=turn.cwd)` (Python `cursor_sdk`). If callers pass cloud runtime options, raise `TypeError` or equivalent programming error — never fall back to cloud.
- **One-shot per turn**: use `Agent.prompt(...)` or async `Agent.create` + one `send` + dispose/close before return. Do not persist a Cursor agent id into LangGraph state or module globals across turns.
- **Auth / settings**: `api_key` from `CURSOR_API_KEY` env only. Do not read `cascade.toml` or document `model` / `models` frontmatter. `setting_sources` empty / not loaded.
- **MCP**: only `turn.tools` — no ambient MCP servers added by the adapter.
- **Errors**:
  - `CursorAgentError` (or a thin wrapper) for startup failures (agent never started): distinct typed error preserving SDK `retryable` / `is_retryable`. This is **not** a `RoleResult`.
  - `RoleResult` with `status == "error"` when a run executed and failed.
- **Async client only** in this module: War Room / watchdog process must not construct the sync default Python SDK client here. Use the async SDK entrypoints (`await Agent.prompt(...)` or async context manager) consistent with `cursor-sdk` docs.
- **`pyproject.toml`**: add `cursor-sdk` to `[project].dependencies` if that is the Python package name.
- **`tests/agent/test_adapter.py`** (or equivalent): mock `cursor_sdk` / `Agent`; no live network. Cover blank `model_id`, cloud-option rejection, startup error vs finished run error, agent disposed before return, and `model_id` forwarded verbatim to SDK options.

## Files likely touched

- `cascade/agent/adapter.py`
- `cascade/agent/types.py` (or colocated types)
- `cascade/agent/__init__.py`
- `tests/agent/test_adapter.py`
- `pyproject.toml`

## Implementation notes

Keep the adapter free of graph, git, scratch-dir, and registry wiring — those land in task_046–task_048. Tool effects can be collected via hooks the sandbox task adds; this task may return an empty list until MCP wrappers exist. If `cursor-sdk` cannot be installed in CI/dev yet, still declare the dependency and structure imports so tests patch the SDK module.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/agent/test_adapter.py -q`

## Out of scope

- Scratch directories and MCP wrappers over Cascade tools (task_046).
- SWE worktree cwd, post-run path checks, commits (task_047).
- Epic / feature / task / boss graph node rewiring (task_048).
- Project default models and document overrides (feat_010).
