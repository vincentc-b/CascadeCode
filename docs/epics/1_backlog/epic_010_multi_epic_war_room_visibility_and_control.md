---
id: epic_010
title: Multi-epic War Room visibility and control
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-22'
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Multi-epic War Room visibility and control

## Intent

Make concurrent epic execution a first-class War Room workflow. Operators should be able to activate and monitor more than one epic without an implicit single-current-epic assumption, while retaining a clear, deliberate context for navigation and chat.

### Success criteria

- When several epics are active, the War Room presents an explicit All active epics overview and never silently treats the lexicographically first epic as the operator's current context.
- Each active epic exposes useful runtime state, including whether its team is queued, running, idle, awaiting human action, blocked, or failed, plus its active features, tasks, reviews, and path-overlap warnings.
- The operator can select an epic, switch among epic and feature conversations, and return or reload without losing the selected context. Switching the visible or compose context does not pause, detach, or otherwise affect work running in another graph.
- The UI clearly distinguishes the single conversation receiving a new human message from the set of independently running or monitored graphs.
- Activating a second eligible epic remains supported and independent: each epic continues to use its own branch, worktree, queue, checkpoint, and serialized graph turn.
- Any workspace/provider concurrency limit is explicit, configurable, and visible in the War Room; reaching it queues work with an explanation rather than creating ambiguous or apparently stuck state.
- API, browser, restart, and multi-epic integration coverage proves selection, runtime-state reporting, concurrent progress, and backward-compatible behavior when zero or one epic is active.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Preserve Git-backed lifecycle state and the existing per-graph worktree, queue, checkpoint, and locking boundaries. Do not introduce a process-global current epic or switch the operator checkout. Board selection and chat attachment are presentation/control concerns and must not own execution lifetime. Keep the single-epic experience simple and backward compatible. Prefer extending the board/flight/runtime APIs and existing focus model over adding a second status store. Runtime health must come from durable or authoritative execution signals, not be inferred solely from board columns. Independent epics must not be serialized unless an explicit configured capacity limit requires it.

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
