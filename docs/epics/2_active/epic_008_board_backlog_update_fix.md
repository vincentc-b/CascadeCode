---
id: epic_008
title: Board backlog update fix
tier: epic
status: active
parent: null
children:
- feat_006
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-21'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Board backlog update fix

## Intent

The war room board currently doesn't update if we are working on a feature/epic branch. I suspect this is because main can't be pulled - our worktree is ahead. So, there probably needs to be a war room "backlog" worktree or something that can always pull main, or maybe otherwise just fetch via API - use your best judgement.

### Success criteria

A brief that was merged on main while an epic/feature was in flight is visible shortly (seconds) after the merge occured, and is available for dispatch.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

To be refined by the Epic Team during planning.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_006

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
