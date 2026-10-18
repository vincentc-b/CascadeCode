---
id: task_052
title: Model resolution boot and turn wiring
tier: task
status: completed
parent: feat_010
children: []
depends_on:
  - task_051
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Model resolution boot and turn wiring

## Parent Feature

[feat_010](../../features/3_completed/feat_010_model_defaults_and_overrides.md) — Model defaults and overrides.

## Depends on

- task_051 — `resolve_model`, `ResolvedModel`, `ModelConfigError`

## Acceptance criteria

- **Epic boot** (`cascade/epic/boot.py` + `cascade/epic/graph.py`):
  - After `read_doc` for the epic, before `ensure_epic_graph` / graph turn, call `resolve_model("epic_manager", doc.meta, root=...)` and `resolve_model("epic_architect", doc.meta, root=...)`.
  - On `ModelConfigError`, do **not** compile or invoke the graph; surface failure to the operator (mirror fail-closed boot patterns — e.g. skip `ensure_epic_graph` and avoid queue ingest that assumes a live graph; extend epic runtime tests accordingly).
  - Seed graph state so `_manager_node` / `_architect_node` use the **per-role** resolved ids (extend `EpicGraphState` / session bootstrap if a single `model_id` field is insufficient for split `models` map overrides).
- **Feature boot** (`cascade/feature/boot.py`, `cascade/feature/graph.py`): same pattern for `feature_lead` and `feature_architect` against the feature document.
- **Task boot** (`cascade/task/boot.py`, `cascade/task/graph.py`):
  - Resolve `swe` against the task document before `ensure_task_graph`.
  - On `ModelConfigError`, call `fail_closed_boot(work_id, reason=...)` and return without compiling the task graph (same class of behavior as stale `parent_rev`).
- **Boss** (`cascade/boss/wiring.py`, `cascade/boss/model_turn.py`, `cascade/war_room/sidecar_routes.py`):
  - Resolve `boss` with `resolve_model("boss", None, root=...)` when the War Room request does not supply a non-blank `model_id` (HTTP body override remains allowed).
  - Boss never reads a work document for model overrides.
- **Prompt visibility** (`cascade/agent/graph_turn.py` and/or `format_turn_prompt` callers):
  - Include the resolved **model id** and **source** (`document-role`, `document`, `project-role`, `project-tier`, `boss-falls-back-to-epic`) in the text passed to planning/SWE turns so the assignment is visible before feat_009 runs.
  - The same resolved id is the `model_id` argument passed into `run_planning_role_turn` / `run_epic_planning_turn` / `run_feature_planning_turn` / `run_boss_planning_turn` / task `swe_turn` → `run_role` (`RoleTurn.model_id`).
- **War Room chat wiring** (`cascade/epic/wiring.py`, `cascade/feature/wiring.py`): when `accept_human_chat` / `accept_feature_human_chat` receives no explicit `model_id`, resolve from the target work doc via `resolve_model` for the role about to run (do not read TOML in planning sandbox code — resolution happens in Cascade wiring only).
- **Graph nodes** (`cascade/epic/graph.py`, `cascade/feature/graph.py`, `cascade/task/graph.py`) continue to **not** read `cascade.toml` directly; they consume caller-supplied ids from state/wiring.
- **Tests** (extend existing runtime/graph suites, inject fakes as today):
  - `tests/watchdog/test_config.py` unchanged behavior for `task_parallelism`
  - `tests/epic/test_runtime.py`, `tests/feature/test_runtime.py`, `tests/task/test_runtime.py`: boot with valid `cascade.toml` `[models]` seeds turns; missing config → graph not started / `fail_closed_boot`
  - `tests/epic/test_graph.py`, `tests/feature/test_graph.py`, `tests/task/test_graph.py`: per-role ids flow to mocked planning/SWE; prompt or message contains source label
  - `tests/boss/test_model_turn.py` or boss wiring tests: boss fallback to epic tier default when `[models].boss` omitted

## Files likely touched

- `cascade/epic/boot.py`
- `cascade/feature/boot.py`
- `cascade/task/boot.py`
- `cascade/epic/graph.py`
- `cascade/feature/graph.py`
- `cascade/task/graph.py`
- `cascade/epic/state.py` / `cascade/feature/state.py` / `cascade/task/state.py` (if per-role model fields needed)
- `cascade/epic/wiring.py`
- `cascade/feature/wiring.py`
- `cascade/boss/wiring.py`
- `cascade/boss/model_turn.py`
- `cascade/agent/graph_turn.py`
- `cascade/war_room/sidecar_routes.py` (only if boss default resolution belongs here vs wiring)
- `tests/epic/test_runtime.py`
- `tests/feature/test_runtime.py`
- `tests/task/test_runtime.py`
- `tests/epic/test_graph.py`
- `tests/feature/test_graph.py`
- `tests/task/test_graph.py`
- `tests/boss/test_model_turn.py`

## Implementation notes

Feat_009 remains the only SDK inference path: wiring calls `resolve_model` then passes ids into existing turn helpers. Dispatch law and `depends_on` are unchanged. Do not store Cursor agent ids in LangGraph checkpoint state. Optional explicit `model_id` on `ingest_human` / sidecar POST may override resolution for that turn when non-blank.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_runtime.py tests/feature/test_runtime.py tests/task/test_runtime.py tests/epic/test_graph.py tests/feature/test_graph.py tests/task/test_graph.py tests/boss/test_model_turn.py -q`

## Out of scope

- Implementing or changing the SDK adapter (`cascade/agent/adapter.py` `run_role`) beyond consuming `model_id`
- Board schema changes (task_050) or TOML reader (task_049)
- Model catalog UI / board filtering (feat_011)
- Cloud agents or mid-turn model changes
