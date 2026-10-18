---
id: task_074
title: Claude and Codex local CLI adapters
tier: task
status: completed
parent: feat_015
children: []
depends_on:
  - task_073
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-16
updated: 2026-10-16
---

# Claude and Codex local CLI adapters

## Parent Feature

[feat_015](../../features/3_completed/feat_015_provider_backends.md) — Provider backends and credentials.

## Depends on

- task_073 — `RoleTurn.provider`, credential resolver, registry dispatch shell in `run_role`

## Acceptance criteria

- **New modules** (suggest `cascade/agent/claude_cli.py`, `cascade/agent/codex_cli.py`, orchestrated from `cascade/agent/adapter.py`):
  - Local **one-shot subprocess** only: process **exits before** `run_role` returns. No TTY, tmux, attach, or cloud VM.
  - `cwd = turn.cwd` for every launch (`subprocess` or `asyncio.create_subprocess_exec` with `cwd=`).
  - Prompt delivered via stdin and/or documented non-interactive flags; **stdout** (and stderr handling documented) becomes `RoleResult.text` on success.
  - **Non-interactive / print / exec mode only.** Interactive TUI invocation is a programming error → typed error (e.g. `ProviderCliError`), not a hung turn.
- **`run_role` dispatch**:
  - When `turn.provider == "claude"`, invoke Claude adapter; when `"codex"`, invoke Codex adapter; when `"cursor"`, keep existing SDK path from task_073.
  - Use `resolve_credential` token/env semantics already wired; adapters must not read workspace or `cascade.toml` for secrets.
  - Still require installed probe + credential before spawn (task_073 gates).
- **Planning / boss roles** (`epic_manager`, `epic_architect`, `feature_lead`, `feature_architect`, `boss`):
  - Must host Cascade **guarded tools** (MCP config equivalent to `build_planning_mcp_servers` / scratch cwd from `cascade/agent/planning_turn.py` and `planning_sandbox.py`).
  - If the CLI version cannot load the supplied MCP config, **fail closed** with a typed error (e.g. `ProviderToolHostError`) — **never** run a tool-less planning turn.
- **SWE role** (`swe`):
  - `cwd` is the task worktree (callers already set via `cascade/task/swe_turn.py`); adapter does not change git/merge semantics.
- **Argv contract** (implementer must verify on machine when binaries exist):
  - Feature spec suggests: Claude → subprocess in **print mode** (feat_015: `` `claude -p` / print mode ``); Codex → **non-interactive exec** (feat_015: `` `codex exec` ``).
  - **Before shipping**, run `claude --help` and `codex --help` on a dev machine with binaries installed and lock exact flags in code comments + tests. **Do not invent undocumented flags.** If a flag cannot be verified in-repo or from existing codebase comments, implement a **single fail-closed probe** subprocess (e.g. `--version` or documented dry-run) and document in the module that argv must be confirmed against vendor help.
  - Tests must mock subprocess; no live CLI required in CI.
- **CLI-session auth probe** (if distinct from task_073): unknown probe result → **`not_authenticated`**, not a guessed yes (feat_015).
- **Errors**: distinguish not installed / not authenticated / tool-host incapable / nonzero exit / timeout; map to typed exceptions or `RoleResult(status="error")` consistently with Cursor adapter (startup vs executed-run failure).
- **Tests** `tests/agent/test_claude_codex_cli.py` (new):
  - Mock subprocess: prompt forwarded, `cwd` matches `turn.cwd`, process waited to completion before return.
  - Planning role with non-empty MCP mapping: argv or env includes MCP config path when supported; if adapter detects unsupported CLI → typed error, no empty-tools planning path.
  - SWE role uses worktree cwd from fixture `Path`.
  - Reject interactive-mode argv patterns if detectable (document detection strategy).

## Files likely touched

- `cascade/agent/adapter.py`
- `cascade/agent/claude_cli.py` (new)
- `cascade/agent/codex_cli.py` (new)
- `cascade/agent/errors.py`
- `cascade/agent/planning_turn.py` (pass-through only if MCP path must be shared)
- `cascade/agent/mcp_wrappers.py`, `cascade/agent/planning_sandbox.py` (read for MCP JSON paths)
- `cascade/task/swe_turn.py` (ensure `RoleTurn.provider` forwarded)
- `tests/agent/test_claude_codex_cli.py` (new)
- `tests/agent/test_adapter.py` (routing cases)

## Implementation notes

Locked contracts from feat_015:

> Claude and Codex adapters:
> - Cascade-spawned subprocess in **print / exec / non-interactive** mode. `cwd = turn.cwd`. stdin is the turn prompt (or the CLI's equivalent flag). stdout is the result. The process exits before `run_role` returns. No TTY, no tmux, no attach.
> - Planning / boss turns still receive only Cascade's guarded tools (MCP config in the scratch cwd, or the CLI's equivalent). SWE turns still use the task worktree …
> - If a CLI cannot host those tools, `run_role` fails closed with a typed error. Do not silently run a tool-less planning turn.
> - Exact CLI argv is an implementation task. The contract is: local child, one assembled prompt, tool-faithful, dispose-on-return. Interactive `claude` / `codex` TUI invocations are a programming error.

> **Local child, remote weights.** A token or CLI login authenticates inference. Cascade starts a local child for one `run_role` against `turn.cwd`, then reaps it.

> **CLI MCP support varies.** If a given Claude or Codex version cannot load Cascade MCP, that backend cannot run planning or boss turns. Fail closed; do not invent a second unguarded tool path.

**Ambiguity (explicit):** exact MCP flag names for Claude Code and Codex CLI are **not** verified in this repo. Implementer confirms against vendor `--help` when binaries exist; otherwise ship fail-closed behavior and document assumed argv in module docstrings.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/agent/test_claude_codex_cli.py tests/agent/test_adapter.py -q`

## Out of scope

- War Room providers UI (task_075)
- `[providers]` config or `resolve_backend` (task_072)
- Credential store HTTP routes (task_075)
- Installing CLIs or remote agent runtimes
- DESIGN.md sync (task_076)
