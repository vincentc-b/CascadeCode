---
id: task_059
title: Author role skill playbooks
tier: task
status: completed
parent: feat_013
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-13
updated: 2026-10-13
---

# Author role skill playbooks

## Parent Feature

[feat_013](../../features/3_completed/feat_013_role_skills_and_frugal_engineering.md) — Role skills and frugal engineering philosophy.

## Depends on

None.

## Acceptance criteria

- Create exactly five in-repo playbooks under `skills/roles/` (each directory contains one `SKILL.md`):
  - `skills/roles/frugal_engineering/SKILL.md` — shared core from the feature **Philosophy → Core: Frugal engineering & pragmatic quality** section (tests earn their keep, maintenance cost, artifact-driven alignment, continuous succession). Intent must not soften.
  - `skills/roles/product_manager/SKILL.md` — PM brief for scope/prioritization; written for `epic_manager` and `feature_lead` consumption (ruthless prioritization, constraint-driven definition, value assessment, markdown as source of truth).
  - `skills/roles/engineering_manager/SKILL.md` — EM brief **rewritten for Cascade Boss verbs**: sequence work, prefer asynchronous artifact handoffs over ceremony, reject over-engineering in proposals, pragmatic quality guardrails, overlap/briefing when handing off — **no HR tools or people-management fiction** the Boss graph does not have.
  - `skills/roles/software_developer/SKILL.md` — SWE product-engineer brief (economical testing, simplicity first, holistic validation).
  - `skills/roles/code_reviewer/SKILL.md` — pragmatic self-check playbook for SWE before commit (anti-pedantry, testing pushback, approve good-enough); not a separate roster node.
- Each file is **one screen** of agent-oriented markdown. Do **not** paste `DESIGN.md` or the full feature spec.
- Playbooks state that skill content is **context only** and does not widen sandboxes or grant dispatch tools.
- Files are valid UTF-8 and readable from the board repo root (paths match those used in `RoleSkillDefaults` in task_060).

## Files likely touched

- `skills/roles/frugal_engineering/SKILL.md` (new)
- `skills/roles/product_manager/SKILL.md` (new)
- `skills/roles/engineering_manager/SKILL.md` (new)
- `skills/roles/software_developer/SKILL.md` (new)
- `skills/roles/code_reviewer/SKILL.md` (new)

## Implementation notes

Source text is the **Philosophy** sections of feat_013; wording may be tightened for agents but intent must not soften. Architects do not get a PM brief in v1 — only the shared frugal core applies to them via defaults in task_060. Code reviewer guidance is loaded as part of the default SWE stack, not a new LangGraph node.

## Skills

_(none)_

## Test plan

No pytest in this task (content-only). task_060 tests will load these paths; optional manual check: paths exist and are under repo root.

## Out of scope

- Python resolver or wiring (task_060–task_062)
- `cascade.toml` role skill overrides
- War Room UI to edit skills
- New roster roles or graph nodes
