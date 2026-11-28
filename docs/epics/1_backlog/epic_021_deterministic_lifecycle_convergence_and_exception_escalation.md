---
id: epic_021
title: Deterministic lifecycle convergence and exception escalation
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
created: '2026-10-23'
updated: '2026-10-23'
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Deterministic lifecycle convergence and exception escalation

## Intent

Prevent completed work from remaining visibly active or blocking dependents when branch documents, review state, lifecycle events, and worktree copies diverge. Add a periodic, deterministic convergence pass that detects invariant violations, repairs cases with one unambiguous correct outcome, and escalates only genuinely ambiguous cases to the owning epic manager with a compact evidence report.

### Success criteria

- Reproduce and automatically heal the failure where a feature pull request merges with its document still active, a completion event is recorded, and a later local relocation never reaches the epic integration branch.
- On startup and a bounded periodic cadence, compare child terminal state, merged-review state, completion events, registry state, and the authoritative document on the owning integration branch.
- Perform idempotent mechanical repair when the terminal outcome is unambiguous: update or relocate the authoritative document, commit and synchronize through the normal branch service, refresh derived board state, and allow dependents to advance.
- Do not treat an existing completion event or closed review record as proof that document convergence is finished. Repeated passes must safely converge after partial failure or restart.
- Emit structured diagnostics with the violated invariant, evidence, attempted repair, retry count, and next action. Deduplicate incidents and verify that a repair actually changed the live board.
- After bounded mechanical retries, or immediately for conflicts with multiple plausible outcomes, deliver the report to the owning epic manager for resolution. Routine healthy checks must not invoke an agent.
- Cover stale epic copies shadowing completed feature copies, interrupted lifecycle commits, push failures, merge conflicts, and restart recovery with focused tests and token/call-count assertions for the healthy path.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Prefer a non-agentic invariant engine and state machine running inside the existing supervisor reconciliation cadence; healthy scans and known repairs must consume no model tokens.
- Use the owning integration branch as the write target and the filesystem board as lifecycle truth, while treating review records and events as evidence to reconcile rather than independent truth that can short-circuit convergence.
- Serialize repair with the existing per-graph lifecycle lock and reuse the branch synchronization service so commits, fetches, pushes, and failures are structured and retryable.
- Define an explicit allowlist of safe repairs. Never auto-resolve content conflicts, bypass approval/dependency gates, rewrite published history, or infer completion when task/review evidence is incomplete.
- Escalate exceptions through a compact durable report attached to the owning epic; wake the epic manager only on a new or materially changed unresolved incident, with cooldown and retry budgets to control token cost.
- Coordinate with epic_012 supervisor readiness and convergence health: reuse its health surfaces and stall reporting where available, but keep lifecycle repair semantics independently testable and idempotent.
- Preserve user work in dirty operator checkouts and runtime sidecars; all automation must be scoped to managed worktrees and explicit paths.

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
