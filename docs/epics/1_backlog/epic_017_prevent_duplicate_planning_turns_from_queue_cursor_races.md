---
id: epic_017
title: Prevent duplicate planning turns from queue cursor races
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
# Prevent duplicate planning turns from queue cursor races

## Intent

Planning graphs can repeatedly process the same queue events when queue ingestion races with an active model turn. The durable queue cursor may remain behind the queue file, causing each maintenance pass to enqueue another manager/architect cycle, repeat replies to an already-addressed human comment, consume unnecessary model capacity, and prevent the graph from converging to idle. Make queue consumption and planning-turn scheduling converge reliably during normal operation, concurrent comments, and supervisor restart.

### Success criteria

- Each queue event is incorporated into a graph at most once for scheduling purposes, including when a model turn is already running.
- The durable queue cursor advances monotonically and is not lost or overwritten by concurrent graph checkpoints.
- Repeated maintenance ticks with an unchanged queue do not start additional planning turns.
- Agent replies and comment-resolution events do not retrigger a planning turn; a new human comment or reply triggers exactly one authorized turn.
- After a supervisor restart, an interrupted turn resumes at most once and the graph settles to an idle checkpoint.
- Concurrent and restart-focused regression tests reproduce the former loop and verify bounded model invocations, cursor convergence, and preserved event ordering.
- Operational visibility identifies a non-advancing cursor or duplicate kickoff before it becomes an unbounded loop.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Preserve per-graph turn serialization and the watchdog's non-blocking supervision behavior.
- Do not drop human messages or non-comment lifecycle events.
- Keep queue files and existing checkpoints backward compatible; recovery must work for already-active graphs.
- Avoid relying only on in-memory deduplication because restarts must remain safe.
- Keep the fix focused on queue ingestion, cursor/checkpoint consistency, kickoff coalescing, and targeted observability.

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
