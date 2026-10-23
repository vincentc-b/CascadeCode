---
id: epic_012
title: Supervisor readiness and convergence health
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
created: '2026-10-22'
updated: '2026-10-23'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Supervisor readiness and convergence health

## Intent

Make Cascade distinguish HTTP availability from lifecycle automation readiness, and detect when eligible work is not converging. Operators should be told when startup recovery, a stalled consumer, or another subsystem prevents approved features or dependency-ready tasks from dispatching.

### Success criteria

Expose supervisor startup and readiness state; report whether the watchdog and automation reconciliation loops are running; detect dispatchable work that remains unchanged beyond a bounded threshold; emit a durable War Room diagnostic naming the item and observed blocker; keep long model-turn recovery from blocking watchdog startup; and provide a disposable synthetic lifecycle probe that never mutates the live board.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

The filesystem board remains lifecycle truth. Health checks must be read-only against live work except for diagnostic events, must not auto-bypass approval or dependency gates, must avoid spawning duplicate work, and must separate local process liveness from workflow convergence. Reuse Boss View, watchdog cadence, queue cursors, and existing War Room toasts where practical.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
