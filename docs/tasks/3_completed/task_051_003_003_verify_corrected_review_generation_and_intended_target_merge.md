---
id: task_051_003_003
title: Verify corrected review generation and intended-target merge
tier: task
status: completed
parent: feat_051_003
children: []
depends_on:
- task_051_003_002
owners:
- swe
skills: []
parent_rev: 7d7866347ad3f78c939a3c96a361cfa406a3996c
created: '2026-11-26'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify corrected review generation and intended-target merge

## Parent Feature

[feat_051_003](../../features/2_active/feat_051_003.md)

## Depends on

- task_051_003_002

## Acceptance criteria

- Independent postcheck and Boss closeout reread the original review and match corrected source/target heads, target policy and current check-run generation.
- Old green, newer failed run, missing/unknown policy, changed target or approval wait cannot verify.
- Terminal success requires all known required checks green, accepted original review merge and merge SHA on intended Epic target.
- Human merge/publication safeguards and source-linked Watchdog/Boss design/Code navigation remain verified.

## Files likely touched

- `cascade/watchdog/incident_postcheck.py`, `cascade/review.py`, affected Boss closeout/review code and focused postcheck/publication tests.
- `cascade/watchdog/DESIGN.md`, `cascade/boss/DESIGN.md`, `cascade/DESIGN.md`, and affected architecture model, views and contract files.

## Implementation notes

Goal: make independent Watchdog repair postcheck and Boss review closeout consume fresh normalized forge evidence for the exact original review and corrected source/target generation. Required policy must be authoritative for current target; every known required check must have a green result for the corrected source and current check-run/pipeline generation. An old green source, new failed run, changed target, missing policy/result, or approval-only wait cannot verify repair. After green, require forge merge of the original review and prove accepted merge SHA is reachable from the intended Epic target before terminal success. Keep human merge gate, generation-bound Feature repair receipt and existing publication safeguards.

Acceptance: focused Watchdog postcheck, Boss closeout and publication tests cover red→admitted repair→new head pending→green→verified intended-target merge; stale head, check generation, moving target, unknown evidence, terminal disposition and restart. Existing branch-push/rebase validation remains enforced. Update cascade/watchdog/DESIGN.md and cascade/boss/DESIGN.md plus cascade/DESIGN.md boundary link; reconcile affected cascade-watchdog-code and cascade-boss-code nodes and relationships in model.dsl, views.dsl and workspace.contract.json. Record diagram-impact inventory for all four C4 levels, source-linked execution/recovery diagrams, contract validation, pinned render and actual Code navigation/Level up/deep link/pinned-source verification in closeout.

## Skills

_(none)_

## Test plan

Run focused independent postcheck, review generation, Boss closeout and publication safeguard tests. Validate source contract, pinned render and changed Code navigation, Level up, deep link and pinned source.

## Out of scope

No automated PR merge, acceptance based only on local status or relaxation of exact-head publication.
