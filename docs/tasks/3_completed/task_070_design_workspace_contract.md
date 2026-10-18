---
id: task_070
title: Record workspace contract in DESIGN.md
tier: task
status: completed
parent: feat_014
children: []
depends_on:
  - task_066
  - task_067
  - task_068
  - task_069
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-14
updated: 2026-10-14
---

# Record workspace contract in DESIGN.md

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_066 — kickoff gates and `kickoff_turn`
- task_067 — `resolve_doc_worktree` and War Room reads
- task_068 — flight report and overlap toasts
- task_069 — stacked merge targets

## Acceptance criteria

- Update **`DESIGN.md`** to mirror implemented behavior (do not contradict feat_014; align with actual code from tasks 063–069):
  - **New subsection** (recommended **§9.4 Workspace supervisor** or **§11 Workspace contract**): tool vs workspace table; `cascade init` / `cascade up`; product trunk rule; one supervisor per root; local loopback UI; filesystem truth; no second status store.
  - **Branches & worktrees**: document stack `trunk → epic/{id} → feat/{id} → task/{id}`; paths `.cascade/worktrees/{epic|feat|task}_{id}`; board lives in team worktree; `cascade.toml` read at trunk only.
  - **Credentials**: `CURSOR_API_KEY` env-only; `setting_sources` empty; no `.netrc`/dotenv/plan keys; models fail closed / blank init template.
  - **Kickoff table**: boot vs model turn; authorized edges; explicit list of non-kickoff actions (mint, backlog, attach, view plan, idle poll, Boss seeing ready work).
  - **War Room attach/plan**: summarize `resolve_doc_worktree` outcomes including backlog feature attach refusal.
  - **Flight report**: path intersections; no auto-block; overlap toasts informational.
  - **Merge targets**: revise stale **mainline** wording in **§5.3**, **§9** watchdog table, **§10.1** (`task/{id}` review branch), and completion table (~§13 if present): task → `feat/{id}`, feature → `epic/{id}`, epic → trunk on human promote.
- Cross-link **`docs/features/3_completed/feat_014_workspace_contract.md`** once from the new section (relative path from repo root in prose is fine).
- **No product code** beyond doc edits in this task; if implementation drifted from feat_014, document **implemented** behavior and add a one-line “spec delta” bullet under feat_014 Decision log via separate human/amendment process — do not silently rewrite feat_014 body here.
- **Validation**: `DESIGN.md` remains markdown only; no board validate on DESIGN — but ensure no broken internal § references after renumbering.

## Files likely touched

- `DESIGN.md` (§2 non-goals may mention single-repo supervisor explicitly; §5.3, §9, §10.1, new workspace section)
- Optional one-line entry in `docs/features/3_completed/feat_014_workspace_contract.md` **Decision log** noting DESIGN sync date (minimal)

## Implementation notes

- Read final implementations in `cascade/workspace/*`, `cascade/cli.py`, `cascade/boss/merge.py`, `cascade/war_room/server.py` before writing — this task is last in the feature wave.
- **Risk (section numbering)**: if adding §11, update any “see §X” pointers that would break; grep `DESIGN.md` for cross-refs.
- **Risk (historical completed features)**: do not bulk-edit `docs/features/3_completed/*`; DESIGN is the canonical forward contract.

## Skills

_(none)_

## Test plan

Manual: reviewer diff against feat_014 API contracts section. Optional: `python3 -m pytest tests/ -q` smoke (no new tests required).

## Out of scope

- Implementing init/up/worktrees/kickoff/flight/merge (prior tasks)
- Publishing docs outside the repo
