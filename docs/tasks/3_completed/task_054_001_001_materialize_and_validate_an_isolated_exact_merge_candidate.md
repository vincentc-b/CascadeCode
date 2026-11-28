---
id: task_054_001_001
title: Materialize and validate an isolated exact merge candidate
tier: task
status: completed
parent: feat_054_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 3c27f075da06d9f914f9494b8ce296406ca2641f
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Materialize and validate an isolated exact merge candidate

## Parent Feature

[feat_054_001](../../features/2_active/feat_054_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Purpose
Build a production Git-backed candidate materialization and fresh validator adapter for the exact source/target pair. Keep the existing review profile and Task command untouched.

## Acceptance
- In a temporary private Git checkout, resolve the freshly observed source and target SHAs into one prospective result commit/tree using Git's real merge path. Return exact commit/tree identity or a typed missing, unknown, or conflict refusal. Preserve operator and team worktrees, refs, index, and caches; remove only owned temporary resources.
- Scan physical lifecycle documents in the candidate before process spawn using Teams-owned validate_publication_board and Board-owned parse_doc. A malformed or duplicate document refuses validation.
- Run the approved argv and coverage in the candidate with finite timeout, process-group cancellation, bounded sanitized diagnostics, effective Python import/source path and dependency identity pinned to candidate bytes. Do not reuse or read stale generated/bytecode across runs; do not delete shared caches. Distinguish product assertion, fixture/environment, timeout, and unavailable evidence with finite owner action.
- Real Git regression: source command green; target adds an incompatible Task boot assertion; candidate fails at that assertion; corrected exact bytes go green. Equal-size same-second Python edits must exercise red then green. Retain product assertion through fixture correction.
- Preserve review_rebase and Task delivery behavior; focused tests in tests/test_review_publication_safeguards.py and tests/test_review_rebase.py use production adapters.
- Update cascade/DESIGN.md for exact candidate and validator execution/recovery flow, and cascade/workspace/DESIGN.md if a public checkout lifecycle interface is added. Extend element.component.teams in cascade-teams-code and cascade-team-components, plus cascade-workspace-code if materialization is Workspace-owned; update model.dsl, views.dsl and workspace.contract.json together, with real symbols and declaration kinds. No new container or validator owner. Verify source contract, pinned render, navigation to Code and source, reverse/deep-link navigation, warm cache and render bounds; record measured checks and gaps. Context/containers remain unchanged because no actor, runtime/data boundary or external dependency is added.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
