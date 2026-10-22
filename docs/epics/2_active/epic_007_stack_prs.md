---
id: epic_007
title: Stack PRs
tier: epic
status: active
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Stack PRs

## Intent

When triggering an epic, currently features will be launched one by one. Feature N+1 won't be implemented before feature N is merged. If feature N is complete, and N+1 is approved, we could instead created stacked PRs and review them sequentially. Once N merges, N+1 should repoint to main automatically, and GitHub should handle this already.

### Success criteria

-Any approved feature is dispatched if its priors are completed and can be stacked.
-The PR's target branch will be the preceding feature's branch if not merged

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

To be refined by the Epic Team during planning.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
