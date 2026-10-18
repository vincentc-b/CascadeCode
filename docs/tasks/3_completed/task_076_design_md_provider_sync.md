---
id: task_076
title: DESIGN.md provider and credentials sync
tier: task
status: completed
parent: feat_015
children: []
depends_on:
  - task_075
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-16
updated: 2026-10-16
---

# DESIGN.md provider and credentials sync

## Parent Feature

[feat_015](../../features/3_completed/feat_015_provider_backends.md) — Provider backends and credentials.

## Depends on

- task_075 — implemented War Room providers flow and credential store (documentation must match shipped behavior)

## Acceptance criteria

- **`DESIGN.md` §2 (Goals / Non-goals)**:
  - **Keep** non-goals that forbid remote agent runtimes and cloud checkpointers (wording may clarify "remote agent runtime" stays out of v1; do **not** remove or soften "Local only" / "Cloud checkpointers or remote agent runtimes").
  - Do **not** contradict feat_015 locked call: **No remote agent runtime.**
- **`DESIGN.md` §9.4 (Workspace supervisor)** — update **Credentials and models** subsection (currently lines ~474–478) to reflect multi-provider reality:
  - Three backends: `cursor` (Python `cursor-sdk`), `claude` and `codex` (local CLIs when on PATH; Cascade does not install them).
  - Credential resolution order: process env (`CURSOR_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) → user-level `~/.cascade/credentials` (mode 0600, written by War Room Providers pane) → CLI login session for Claude/Codex only; Cursor v1 has no CLI-session source.
  - Explicit **never** list: not in repo, not `cascade.toml`, not plans, not dotenv, not `.netrc`, not workspace.
  - Model ids: per-provider tables in trunk `cascade.toml` `[providers]` (legacy `[models]` = cursor table when `[providers]` absent); document frontmatter `provider` / `model` / `models`; blank `init` template fails closed; no inheritance from parent epic/feature.
  - War Room Providers pane: localhost-only token paste/forget; GET never echoes secrets.
  - **`init` bullet**: describe new `[providers]` scaffold (from task_073), not only `[models]`.
- **Cross-links**: if §9.4 references feat_014 only for workspace contract, add a pointer to `docs/features/3_completed/feat_015_provider_backends.md` without duplicating the full spec.
- **Consistency pass**: grep `DESIGN.md` for stale single-provider phrases (e.g. "One supervisor process, one key" only for Cursor) and update to "one credential resolver per provider" without implying cloud agents or multi-tenant SaaS.
- **No code changes** required beyond docs unless a comment in `cascade/workspace/init.py` or module docstrings explicitly claims old CURSOR-only contract — if so, one-line docstring alignment only (optional, minimal).

## Files likely touched

- `DESIGN.md`
- (optional) `cascade/workspace/init.py` module docstring if it references only `[models]`

## Implementation notes

Locked contracts from feat_015 (documentation must not weaken):

> 2. **No remote agent runtime.** … Durable memory is the LangGraph checkpointer and the markdown board. … Rejected.

> 4. **Login is in-app and user-scoped.** … Environment variables still win (CI / headless). The War Room can store a token under `~/.cascade/credentials` (mode `0600`).

> **Do not install CLIs.** Missing `claude` or `codex` is a status of `not_installed`, not an installer prompt.

Task breakdown item from feat_015: **§2 non-goals stay "no remote agent runtime"; §9.4 credentials become multi-provider + user-level store.**

Do not reopen epic locked calls (`dec_019` items in feat_015).

## Skills

_(none)_

## Test plan

No pytest required. Manual review: `rg -n 'CURSOR_API_KEY|\\[models\\]|remote agent' DESIGN.md` shows updated §9.4 and unchanged §2 non-goals.

## Out of scope

- Feature spec or epic amendments
- Operator-facing README unless it duplicates DESIGN §9.4 (only change DESIGN unless user asks)
- Implementing provider behavior (prior tasks)
