---
id: epic_030
title: Return an unstarted Epic to backlog
tier: epic
status: completed
parent: null
children:
- feat_030_001
- feat_030_002
- feat_030_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-31'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
plan_approved_at: '2026-11-01T21:46:15.045303+00:00'
---
# Return an unstarted Epic to backlog

## Intent

An Epic can be activated before its pinned provider proves usable. `epic_028` is active with Cursor, but planning cannot proceed because Cursor is not authenticated. Give an operator a safe, human-only **Return to backlog** action for an active Epic and its full descendant graph, so the approved brief can be revised through the existing reviewed backlog-edit flow and the same Epic, Features, and Tasks can later be reactivated with corrected provider/model choices and an explicit freshness review.

This is a lifecycle correction, not cancellation, plan reset, or an in-place provider edit.

### Success criteria

- Show **Return to backlog** on an active Epic when the shared eligibility evaluator proves the Epic and its complete descendant graph can be preserved and transitioned without data loss. Existing children, approved plans, and review history are not disqualifiers; missing graph provenance, unsafe in-flight work, or unpreservable Git state are. Every failed condition is surfaced on the Epic row.
- On request, quiesce all in-flight turns in the Epic descendant graph, acquire lifecycle locks for the graph in deterministic order, and re-evaluate eligibility under those locks before mutation.
- Execute a durable, restart-safe, idempotent transition with one audit event. Retries return the recorded result and never duplicate checkpoints, branches, worktrees, backlog briefs, or events.
- Move the same Epic and every descendant to backlog as one graph-preserving operation, remove their active board pointers, and expose the Epic's existing MR-backed backlog editor.
- Preserve or archive the former integration branch, worktree, transcripts, and startup-failure evidence. Refuse when dirty files or unmerged commits cannot be preserved without loss. Never reset or switch the operator trunk.
- After an approved provider/model edit merges and backlog refresh completes, reactivation restores the descendant graph, creates fresh run identities and role pins, ignores obsolete checkpoints, and requires each owning agent team to review its plan for staleness before work resumes.
- End-to-end coverage includes the `epic_028` missing-credential shape, concurrent/repeated requests, restart between transition steps, all material refusal cases, reviewed provider editing, and successful Codex reactivation.

## Scope

### In scope

- A human-only API/command and War Room row control for active Epic graph → backlog.
- A single shared, structured eligibility evaluator used for presentation and command enforcement.
- Quiescence, lifecycle locking, durable transition journaling, recovery, idempotency, and audit emission.
- Restoration of the approved source brief through existing backlog storage/refresh behavior.
- Preservation of Epic and descendant artifacts, graph relationships, and history, with invalidation of stale activation state.
- Reuse of the existing reviewed backlog-brief edit and activation flows.

### Out of scope

- Independently returning a Feature or Task while its Epic remains active.
- Destructive rollback, deletion, or erasure of approved plans, child work, review activity, or substantive edits.
- Editing provider/model pins directly on an active Epic.
- Automatic provider fallback, automatic MR creation/merge, cancellation, destructive cleanup, branch deletion, or trunk manipulation.
- A general-purpose lifecycle migration framework beyond the minimum durable transition required here.

## Eligibility contract

Eligibility is evaluated from authoritative persisted state, not UI state. The evaluator returns `eligible` plus stable reason codes and operator-readable explanations.

An Epic is eligible only when all of the following hold:

1. It is currently an active Epic and is not already in another terminal or lifecycle transition.
2. Its complete descendant graph can be enumerated from authoritative state, with stable IDs, parent links, source revisions, approvals, comments, and review history sufficient for deterministic restoration.
3. Every in-flight turn in the graph can be quiesced, and no graph member is already in a conflicting terminal or lifecycle transition.
4. Every Epic/Feature/Task plan, review artifact, amendment, checkpoint, and substantive change can be preserved as history; their existence is not a refusal condition.
5. Every graph member's branch/worktree state can be preserved or archived without data loss. Dirty files or unmerged commits are allowed only when the retention mechanism can prove they remain reachable and restorable.
6. Required Epic source brief, activation provenance, and descendant activation provenance exist so the same graph can be restored deterministically.
7. A deterministic lifecycle-lock order is available for the complete graph.
8. No conflicting lifecycle operation is in progress.

The evaluator must identify every failing condition in one response. The command must run the same evaluator again after quiescence and while holding the lifecycle lock; a stale UI result never authorizes the transition.

## Macro-architecture

### 1. Shared eligibility and presentation

Add a read-only domain service for return eligibility. It consumes the Epic lifecycle record, the complete descendant graph, activation/source references, planning and review state, checkpoints/turn outcomes, and Git status for every graph member. It emits stable reason codes suitable for API clients and a human explanation for each refusal.

Both the API command and War Room row use this service. The row displays the action only to authorized humans for active Epics; when unavailable, it displays the refusal explanation(s) rather than silently hiding the capability.

Approved or substantively changed plans do not block return; they become preserved review inputs. Eligibility is about lossless graph transition and deterministic restoration, not whether work has occurred. Do not infer safety from timestamps or provider-failure status alone.

### 2. Lifecycle command and durable transition

Implement a human-authorized `return_epic_to_backlog(epic_id, request_id)` application command:

1. Resolve an existing completed/in-progress operation by idempotency key or Epic transition record.
2. Resolve the complete descendant graph, request quiescence for every owning team, and wait until no role turn in the graph can still commit state.
3. Acquire lifecycle locks for the Epic and descendants in deterministic graph order.
4. Re-read authoritative state, re-resolve the graph, and re-run the eligibility evaluator; abort if membership changed.
5. Create or resume a durable transition journal keyed by Epic ID with ordered steps and captured source/active provenance.
6. Preserve/archive all graph-member plans, branches, worktrees, transcripts, reviews, comments, diagnostics, and checkpoints without deleting history.
7. Restore/upsert the Epic backlog brief and persist a graph manifest containing descendant identities, relationships, revisions, and prior lifecycle states.
8. Invalidate active-run identities and role pins, remove active board pointers for the whole graph, and atomically publish the graph in backlog state.
9. Commit the lifecycle result and emit exactly one audit event through an outbox/deduplicated event key.

Each step is replay-safe and records completion before advancing. Recovery resumes the journal after process restart. Concurrent requests serialize on the lifecycle lock and converge on the same completed outcome. A request arriving after success reports the recorded success.

No step resets, checks out, or force-updates operator trunk. Failure before commit leaves the Epic visibly active or explicitly transition-pending; it must never present two independently editable authoritative copies.

### 3. Existing backlog edit and fresh activation

The restored item is a normal backlog brief and uses the existing MR-backed editor, approval, merge, and backlog refresh path. This Epic adds no bypass for active-plan metadata.

A later Epic activation reads the newly approved backlog revision and graph manifest, restores all descendants and relationships, creates fresh activation/run identities, and resolves fresh provider/model role pins. Before any resumed implementation, each owning Epic or Feature agent team reviews its restored plan against the revised ancestor contract and records any required amendment or a fresh sign-off. Checkpoint lookup is scoped to the new activation/run identity, so archived runs cannot silently resume. Old artifacts remain evidence and review inputs, not executable activation state.

## State and invariants

- Epic and descendant IDs, graph relationships, approved plans, source history, comments, reviews, and audit history remain stable across the transition.
- Exactly one graph state is authoritative: all members remain active/transition-pending until commit, then all are backlog; partial publication is forbidden.
- A completed transition has one durable result and one audit event.
- Archived run artifacts are evidence and freshness-review inputs, not resumable execution state.
- Refusal is side-effect free except for normal observability.
- Eligibility reason codes are part of the API contract and are shared with the War Room.
- If safety cannot be proven, refuse and explain; never attempt cleanup to manufacture eligibility.

## Cross-module constraints

- Human approval remains required for changing an approved brief; reuse the existing MR-backed backlog edit path.
- Preserve IDs, comments, source revision provenance, and history.
- Do not cancel completed/reviewed work, delete or rewrite dirty artifacts, force-push, or bypass provider, authorization, freshness review, or lifecycle gates.
- Graph-wide quiescence must prevent any descendant role turn from committing after the locked eligibility check.
- Lock ordering must follow existing lifecycle conventions; do not hold the lifecycle lock while waiting for a turn to stop.
- Board refresh and audit delivery may be retried; both must be deduplicated from durable transition identity.
- Failure messages must be actionable without exposing credentials or transcript secrets.

## Core dependencies

- Epic/Feature/Task lifecycle state machines and deterministic multi-entity lifecycle locking.
- Epic and descendant team scheduler/quiescence mechanisms.
- Plan approval/sign-off, child graph, review/amendment, and checkpoint stores.
- Activation provenance and approved backlog brief storage.
- Integration branch/worktree Git inspection and artifact retention.
- Existing backlog MR editor, merge/refresh pipeline, and activation pin resolver.
- Board/War Room API, authorization, audit event/outbox, and recovery runner.

## Feature breakdown
- feat_030_003
- feat_030_002
- feat_030_001

### Feature 1 — Eligibility contract and operator control

Deliver the shared eligibility evaluator, stable refusal reasons, human authorization, API read/command contract, and War Room row behavior. Include focused domain tests for every predicate and an integration test proving presentation and command use identical results.

This feature establishes the safety contract but does not mutate lifecycle state independently of Feature 2.

### Feature 2 — Durable, idempotent active-to-backlog transition

Deliver graph-wide quiescence, deterministic multi-entity locking, locked graph recheck, transition journal, graph manifest and artifact preservation, atomic backlog publication, active-pointer removal, stale-run invalidation, recovery, and exactly-once audit semantics.

High-signal tests cover two concurrent requests, repeated requests after success, graph membership races, injected restart/failure at each durable boundary, descendant turns racing with quiescence, preservable and unpreservable dirty/unmerged Git cases, atomic graph publication, and evidence preservation without operator-trunk changes.

Depends on Feature 1.

### Feature 3 — Reviewed edit and clean reactivation journey

Wire the restored Epic into the existing MR-backed brief editor and verify activation restores the descendant graph with fresh run identities and role pins, then gates resumed work on agent-team freshness review.

One end-to-end scenario models an Epic with approved child Features: return the full graph → reviewed provider/model change → backlog refresh → Codex reactivation → descendant freshness reviews, with archived checkpoints demonstrably ignored. Add refusal journeys for incomplete graph provenance, failed quiescence, and artifacts that cannot be preserved.

Depends on Feature 2.

## Verification strategy

Favor a small number of stateful integration and end-to-end tests over mock-heavy unit coverage:

- Table-driven evaluator tests define graph-preservation eligibility and stable reason codes, including approved plans and children as eligible cases.
- Lifecycle integration tests use real persisted state plus controllable failure injection to validate replay and idempotency at every journal boundary.
- Git/worktree integration tests prove clean preservation and dirty/unmerged refusal without touching trunk.
- A single full journey validates graph return, reviewed edit, descendant restoration, freshness review, and fresh activation.
- Existing cancellation, backlog editing, activation, and audit suites remain regression gates where behavior is shared.

## Rollout and observability

Ship behind a capability flag if lifecycle controls use flags today; otherwise authorization plus strict eligibility is the gate. Record transition ID, Epic ID, actor, prior/new state, source revision, step progress, refusal codes, and deduplicated audit outcome. Never log provider credentials or transcript content.

Operators must be able to distinguish: ineligible, quiescing, transition pending/recovering, completed, and failed with retry safe. A recovery scan resumes incomplete journals on startup.

## Open questions

None blocking. Feature planning should bind the contracts above to existing module names and persistence primitives without widening scope.

## Decision log

- 2026-10-31 · Human · Brief approved through merge request review.
- 2026-11-01 · Epic Manager · Treat Return to backlog as a human-only, graph-preserving lifecycle transition with a shared fail-closed eligibility contract.
- 2026-11-01 · Epic Manager · Use a durable replay-safe transition journal plus lifecycle lock and quiescence; retries converge on one result and one audit event.
- 2026-11-01 · Epic Manager · Preserve the former active run as evidence, restore the approved source brief, and require a new activation identity so stale provider pins cannot resume.

- `dec_001` · 2026-11-01 · Epic Manager · **Lifecycle scope**
  Superseded by the 2026-11-01 descendant-cascade decision in reply to `cmt_001`; the transition is no longer limited to Epics without substantive or child work.

- `dec_002` · 2026-11-01 · Epic Manager · **Transition semantics**
  Chose Use quiescence, a per-Epic lifecycle lock, and a durable replay-safe transition journal with deduplicated audit emission..
  Rationale: A multi-step filesystem and board transition must survive concurrency, retries, and process restarts without duplicate state or data loss.
  Honors: Success criteria 2; restart safety; idempotency; one audit event; operator trunk protection..

- `dec_003` · 2026-11-01 · Epic Manager · **Reactivation boundary**
  Chose Preserve the former active run as evidence, restore the approved source brief, and require a fresh activation identity and role pins..
  Rationale: The reviewed backlog flow must remain authoritative, while stale checkpoints must not reselect the failed provider.
  Honors: Success criteria 3 and 4; preserved history; MR-backed edits; fresh Codex reactivation..

- `dec_004` · 2026-11-01 · Epic Manager · **Lifecycle scope**
  Chose Cascade Return to backlog across the active Epic's complete descendant graph, then restore that graph on reactivation with fresh run identities and mandatory agent-team freshness review..
  Rationale: In reply to: cmt_001. Existing children and reviewed work should be preserved rather than treated as a permanent lifecycle barrier. Atomic graph transition plus review-gated reactivation supports the fringe recovery case without deleting history or silently resuming stale execution.
  Honors: Human request cmt_001; graph preservation; same IDs and relationships; atomic transition; fresh provider pins; explicit staleness review before work resumes..
## Amendment log

_(none)_
