---
id: epic_018
title: Graceful supervisor updates without War Room outage
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
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Graceful supervisor updates without War Room outage

## Intent

Cascade currently detects changes to its loaded Python source and exits with a restart-required error. When the hosting process does not relaunch it, the War Room listener disappears and SSH-forwarded clients receive connection-refused errors until an operator manually restarts the supervisor. Replace this failure mode with a controlled update lifecycle that safely hands off or restarts the supervisor, preserves durable workflow state, and restores service automatically.

### Success criteria

- A detected Cascade source change initiates a controlled restart or process handoff instead of terminating into an unrecovered failure state.
- The War Room automatically resumes listening on the configured host and port without manual intervention.
- In-flight planning and task work is drained when possible or recovered exactly once from durable checkpoints after restart.
- The supervisor lock and listener socket transfer cleanly, with no overlapping active supervisors, orphaned agent subprocesses, or stale-lock blockage.
- New HTTP work is stopped or rejected with an explicit transient updating response during shutdown; accepted writes are not lost.
- Update progress and failures are visible through logs and UI health/status, including actionable diagnostics when automatic recovery cannot complete.
- A failed replacement process leaves the last viable service running when feasible, or retries with bounded backoff rather than silently remaining offline.
- Integration tests exercise source-change detection, active model turns, queued events, port rebinding, failed replacement startup, and successful automatic recovery.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Preserve the existing single-supervisor invariant and product-trunk workspace validation.
- Do not mix old and new Python modules within one long-lived process.
- Treat graph checkpoints, queues, comments, and worktree state as durable handoff boundaries.
- Avoid platform-specific daemon assumptions where possible; define a clear launcher/process contract for environments that host Cascade.
- Bound listener downtime and prevent restart storms through readiness checks, retry limits, and backoff.
- Keep operator-initiated shutdown distinct from source-triggered update restart.

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
