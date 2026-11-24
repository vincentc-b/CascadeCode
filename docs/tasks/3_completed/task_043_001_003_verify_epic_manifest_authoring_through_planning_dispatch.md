---
id: task_043_001_003
title: Verify Epic manifest authoring through planning dispatch
tier: task
status: completed
parent: feat_043_001
children: []
depends_on:
- task_043_001_001
- task_043_001_002
owners:
- swe
skills: []
parent_rev: f281d4e334740f7d7195f13b4eedc22216b07c12
created: '2026-11-07'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify Epic manifest authoring through planning dispatch

## Parent Feature

[feat_043_001](../../features/2_active/feat_043_001.md)

## Depends on

- task_043_001_001
- task_043_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend existing production planning-dispatcher/catalog and boundary integration tests for both Epic roles. Exercise absent/read/create/append/current-revision no-op, explicit none-required and real declarations, malformed/runtime inputs, stale/concurrent/replayed writes, completed/cross-Epic and path/symlink denial, and the actual owning-worktree destination. Cover canonical lock identity when target and tracking repositories differ, fresh software/bootstrap and plan-readiness projections, and unchanged installation/approval authority. Use existing test fixtures and avoid duplicate schema unit tests or external installs. Run the relevant targeted suite and fix any feature-owned gaps it finds.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.

## Final direct delivery · 2026-11-08

Status: completed. Implementation through `a37f05ff` and preceding commits supersedes the earlier partial-completion audit. The operator explicitly requested implementation directly on main because the affected tool could not reliably implement its own repairs. No acceptance criteria are waived.

This existing child plan is satisfied by the Epic 43 implementation delivered directly on main. Its scope, requirements and accepted history are preserved; completion records the operator-authorized direct delivery, not a fabricated Task merge or forge review. The Epic 43 final-delivery section maps the acceptance evidence.

Validation: the combined affected acceptance suite passed 164 tests; additional targeted crash, failure, and cross-process checks passed. This records scoped acceptance, not a claim that every unrelated repository test passes.
