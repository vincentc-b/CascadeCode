---
id: task_022
title: Feature record_decision tool
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_020
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Feature record_decision tool

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_020 — `feature_read_doc` / `feature_write_doc` for own feature only

## Acceptance criteria

- `record_decision(section, choice, rationale, honors, *, feature_id, root, author=...)` appends a formatted bullet to the Feature `## Decision log` and persists via `feature_write_doc`.
- Decision ids are monotonic `dec_NNN` (three digits) within the log section — same formatting rules as epic (`cascade/epic/decisions.py`).
- If `cascade/epic/decisions.py` logic is reusable, extract shared append helper (e.g. `cascade/board/decision_log.py`) and keep epic wrapper thin; otherwise implement a feature-local wrapper that does not invent a second on-disk format.
- `author` values `feature_architect` / `feature_lead` render as Feature Architect / Feature Lead.
- Missing `## Decision log` raises `ValueError` with a clear message.
- Registers on `register_feature_tool` as `record_decision`.
- `tests/feature/test_decisions.py` covers append, id monotonicity, author labels, and deny writing epic files.

## Files likely touched

- `cascade/feature/decisions.py`
- `cascade/board/decision_log.py` (optional shared extract)
- `cascade/epic/decisions.py` (optional refactor to shared helper)
- `tests/feature/test_decisions.py`

## Implementation notes

Do not emit queue events unless DESIGN requires `DecisionRecorded` for features in MVP — if added, enqueue to feature graph only. Match epic bullet shape from feat_004 task_015.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/feature/test_decisions.py tests/feature/test_scoped_docs.py -q`

## Out of scope

- Comment store (task_023)
- `mint_task` (task_021)
- Package `cascade/feature/__init__.py` export surface (task_024 wiring)
