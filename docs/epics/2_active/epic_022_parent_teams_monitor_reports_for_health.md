---
id: epic_022
title: Parent teams monitor reports for health
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
created: '2026-10-23'
updated: '2026-10-25'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Parent teams monitor reports for health

## Intent

It's happened that tasks got to a stuck state. In this case, the supervising team should try to fix and if they cannot, they should themselves to got "stuck" state to mirror the children

### Success criteria

-Supervisors monitor their reports (e.g. epics monitor features who monitor tasks) by periodically looking at their states
-If a problem is encountered (e.g. stuck task), the parent team attempt to fix
-If a fix is not possible, they will flag their own state as "stuck" (or whatever, to reflect report's state)

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

- 2026-10-23 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
