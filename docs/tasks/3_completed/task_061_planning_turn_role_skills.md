---
id: task_061
title: Planning turn role skills wiring
tier: task
status: completed
parent: feat_013
children: []
depends_on:
  - task_060
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-13
updated: 2026-10-13
---

# Planning turn role skills wiring

## Parent Feature

[feat_013](../../features/3_completed/feat_013_role_skills_and_frugal_engineering.md) — Role skills and frugal engineering philosophy.

## Depends on

- task_060 — `load_role_skills_context`, `resolve_effective_skills`, `default_role_skill_paths`

## Acceptance criteria

- **Epic planning** (`cascade/epic/graph.py`, `cascade/agent/planning_turn.py` / epic turn entrypoints): before `run_role` / `run_epic_planning_turn`, load playbooks via `load_role_skills_context(root, role, task_skills=None)` for `epic_manager` and `epic_architect` nodes.
- **Feature planning** (`cascade/feature/graph.py`, feature planning turn helpers): same for `feature_lead` and `feature_architect`.
- **Boss** (`cascade/boss/model_turn.py`, `cascade/boss/graph.py` or wiring): load defaults for `boss` only; no work document `skills`.
- **Prompt injection** (`cascade/agent/graph_turn.py` `format_turn_prompt` and/or `build_boss_prompt`):
  - Prepend or append loaded playbook **text** to the role prompt for that turn.
  - Include a **visible list of loaded role-skill paths** in the prompt (same spirit as resolved model id + source visibility from feat_010 / task_052).
  - v1 builds playbook context **ephemerally per turn** (no new LangGraph checkpoint fields required for role skills on epic/feature/boss state).
- Planning roles must **not** read Task frontmatter `skills`; only role defaults from task_060 apply.
- **Tests** (extend or add; use fakes/mocks for `run_role` as existing graph tests do):
  - `tests/epic/test_graph.py`: prompt passed to planning turn contains distinctive substring from a fixture playbook and lists path(s).
  - `tests/feature/test_graph.py`: same for feature roles.
  - `tests/boss/test_model_turn.py` (or boss graph tests): boss prompt includes EM/frugal playbook text and path visibility.
  - Fail-closed: if `load_role_skills_context` would raise (missing playbook file), graph turn does not call `run_role` with a silent empty philosophy block (mirror model fail-closed boot patterns where applicable).

## Files likely touched

- `cascade/agent/graph_turn.py`
- `cascade/agent/planning_turn.py`
- `cascade/epic/graph.py`
- `cascade/feature/graph.py`
- `cascade/boss/model_turn.py`
- `cascade/boss/graph.py` (if boss turn assembly lives here)
- `tests/epic/test_graph.py`
- `tests/feature/test_graph.py`
- `tests/boss/test_model_turn.py`

## Implementation notes

Reuse task_060 APIs only; do not duplicate path validation. Skill content is context only — must not widen planning sandboxes or add dispatch tools. No new HTTP routes or queue event types.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_graph.py tests/feature/test_graph.py tests/boss/test_model_turn.py -q`

## Out of scope

- Task SWE boot / `skill_playbooks` state (task_062)
- Storing playbook text in epic/feature checkpoint state (optional later)
- War Room UI changes
