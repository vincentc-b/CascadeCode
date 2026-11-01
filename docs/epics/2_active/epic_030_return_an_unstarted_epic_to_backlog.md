---
id: epic_030
title: Return an unstarted Epic to backlog
tier: epic
status: active
parent: null
children:
- feat_030_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-31'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Return an unstarted Epic to backlog

## Intent

An Epic can be activated before its pinned provider proves usable. `epic_028` is active with Cursor, but planning cannot proceed because Cursor is not authenticated. Give an operator a safe, human-only **Return to backlog** action for an Epic that has done no substantive work, so its approved brief can be revised through the existing reviewed backlog-edit flow and activated again with corrected provider/model choices.

This is a lifecycle correction, not cancellation, plan reset, or an in-place provider edit.

### Success criteria

- Show **Return to backlog** on an active Epic only when the shared eligibility evaluator proves that no approved plan, child/review work, or substantive plan change would be lost. Failed startup attempts alone remain eligible. Every failed condition is surfaced on the Epic row.
- On request, quiesce in-flight Epic turns, acquire the Epic lifecycle lock, and re-evaluate eligibility under that lock before mutation.
- Execute a durable, restart-safe, idempotent transition with one audit event. Retries return the recorded result and never duplicate checkpoints, branches, worktrees, backlog briefs, or events.
- Restore the same Epic ID and approved source brief to backlog, remove its active board pointer, and expose the existing MR-backed backlog editor.
- Preserve or archive the former integration branch, worktree, transcripts, and startup-failure evidence. Refuse when dirty files or unmerged commits cannot be preserved without loss. Never reset or switch the operator trunk.
- After an approved provider/model edit merges and backlog refresh completes, reactivation creates fresh role pins and ignores obsolete active-run checkpoints.
- End-to-end coverage includes the `epic_028` missing-credential shape, concurrent/repeated requests, restart between transition steps, all material refusal cases, reviewed provider editing, and successful Codex reactivation.

## Scope

### In scope

- A human-only API/command and War Room row control for active Epic → backlog.
- A single shared, structured eligibility evaluator used for presentation and command enforcement.
- Quiescence, lifecycle locking, durable transition journaling, recovery, idempotency, and audit emission.
- Restoration of the approved source brief through existing backlog storage/refresh behavior.
- Preservation of active-run artifacts and invalidation of stale activation state.
- Reuse of the existing reviewed backlog-brief edit and activation flows.

### Out of scope

- Returning Features or Tasks to backlog.
- Rolling back an Epic after plan approval, child creation, review activity, or substantive plan edits.
- Editing provider/model pins directly on an active Epic.
- Automatic provider fallback, automatic MR creation/merge, cancellation, destructive cleanup, branch deletion, or trunk manipulation.
- A general-purpose lifecycle migration framework beyond the minimum durable transition required here.

## Eligibility contract

Eligibility is evaluated from authoritative persisted state, not UI state. The evaluator returns `eligible` plus stable reason codes and operator-readable explanations.

An Epic is eligible only when all of the following hold:

1. It is currently an active Epic and is not already in another terminal or lifecycle transition.
2. No Epic plan has been approved or signed off.
3. No child Feature/Task, review artifact, amendment, or other downstream work exists.
4. The active plan body has no substantive divergence from the activation baseline. Mechanical lifecycle metadata, generated placeholders, startup attempt records, and failure diagnostics do not count as substantive changes.
5. No successful substantive role turn or resumable planning checkpoint exists. Failed startup attempts that produced no plan mutation are allowed.
6. The integration worktree is clean and the integration branch has no unmerged commits that would be discarded or made unreachable by the transition.
7. Required source brief and activation provenance exist so the same Epic can be restored deterministically.
8. No conflicting lifecycle operation is in progress.

The evaluator must identify every failing condition in one response. The command must run the same evaluator again after quiescence and while holding the lifecycle lock; a stale UI result never authorizes the transition.

## Macro-architecture

### 1. Shared eligibility and presentation

Add a read-only domain service for return eligibility. It consumes the Epic lifecycle record, activation baseline/source reference, planning/review/child state, checkpoints/turn outcomes, and integration Git status. It emits stable reason codes suitable for API clients and a human explanation for each refusal.

Both the API command and War Room row use this service. The row displays the action only to authorized humans for active Epics; when unavailable, it displays the refusal explanation(s) rather than silently hiding the capability.

Substantive plan divergence is determined by comparing canonical plan content with the recorded activation baseline while excluding an explicit, narrow set of lifecycle-managed fields. Do not infer safety from timestamps or failed-provider status alone.

### 2. Lifecycle command and durable transition

Implement a human-authorized `return_epic_to_backlog(epic_id, request_id)` application command:

1. Resolve an existing completed/in-progress operation by idempotency key or Epic transition record.
2. Request quiescence for the Epic team and wait until no role turn can still commit state.
3. Acquire the per-Epic lifecycle lock.
4. Re-read authoritative state and re-run the eligibility evaluator.
5. Create or resume a durable transition journal keyed by Epic ID with ordered steps and captured source/active provenance.
6. Preserve/archive active-run artifacts without deleting branches, worktrees, transcripts, or diagnostics.
7. Restore/upsert the backlog brief from the approved source content under the same Epic ID.
8. invalidate active-run checkpoints and role pins for future activation, remove the active board pointer, and publish the backlog state.
9. Commit the lifecycle result and emit exactly one audit event through an outbox/deduplicated event key.

Each step is replay-safe and records completion before advancing. Recovery resumes the journal after process restart. Concurrent requests serialize on the lifecycle lock and converge on the same completed outcome. A request arriving after success reports the recorded success.

No step resets, checks out, or force-updates operator trunk. Failure before commit leaves the Epic visibly active or explicitly transition-pending; it must never present two independently editable authoritative copies.

### 3. Existing backlog edit and fresh activation

The restored item is a normal backlog brief and uses the existing MR-backed editor, approval, merge, and backlog refresh path. This Epic adds no bypass for active-plan metadata.

A later activation reads the newly approved backlog revision, creates a new activation/run identity, and resolves fresh provider/model role pins. Checkpoint lookup is scoped to the activation/run identity so the archived active run cannot select Cursor or otherwise resume. The old branch/worktree and failure evidence remain available according to existing retention policy, but are not activation inputs.

## State and invariants

- Epic ID, approved source history, comments, and audit history remain stable across the transition.
- Exactly one state is authoritative for editing: active until the journal commits; backlog afterward.
- A completed transition has one durable result and one audit event.
- Archived active-run artifacts are evidence, not inputs to later activation.
- Refusal is side-effect free except for normal observability.
- Eligibility reason codes are part of the API contract and are shared with the War Room.
- If safety cannot be proven, refuse and explain; never attempt cleanup to manufacture eligibility.

## Cross-module constraints

- Human approval remains required for changing an approved brief; reuse the existing MR-backed backlog edit path.
- Preserve IDs, comments, source revision provenance, and history.
- Do not cancel completed/reviewed work, delete dirty artifacts, force-push, or bypass provider, authorization, review, or lifecycle gates.
- Quiescence must prevent a role turn from committing after the locked eligibility check.
- Lock ordering must follow existing lifecycle conventions; do not hold the lifecycle lock while waiting for a turn to stop.
- Board refresh and audit delivery may be retried; both must be deduplicated from durable transition identity.
- Failure messages must be actionable without exposing credentials or transcript secrets.

## Core dependencies

- Epic lifecycle state machine and per-Epic lifecycle lock.
- Epic-team turn scheduler/quiescence mechanism.
- Plan approval/sign-off, child graph, review/amendment, and checkpoint stores.
- Activation provenance and approved backlog brief storage.
- Integration branch/worktree Git inspection and artifact retention.
- Existing backlog MR editor, merge/refresh pipeline, and activation pin resolver.
- Board/War Room API, authorization, audit event/outbox, and recovery runner.

## Feature breakdown
- feat_030_001

### Feature 1 — Eligibility contract and operator control

Deliver the shared eligibility evaluator, stable refusal reasons, human authorization, API read/command contract, and War Room row behavior. Include focused domain tests for every predicate and an integration test proving presentation and command use identical results.

This feature establishes the safety contract but does not mutate lifecycle state independently of Feature 2.

### Feature 2 — Durable, idempotent active-to-backlog transition

Deliver quiescence, locked recheck, transition journal, artifact preservation, backlog restoration, active-pointer removal, stale-run invalidation, recovery, and exactly-once audit semantics.

High-signal tests cover two concurrent requests, repeated requests after success, injected restart/failure at each durable boundary, a turn racing with quiescence, dirty/unmerged Git refusal, and preservation of evidence without operator-trunk changes.

Depends on Feature 1.

### Feature 3 — Reviewed edit and clean reactivation journey

Wire the restored Epic into the existing MR-backed brief editor and verify activation consumes the merged backlog revision with a fresh run identity and fresh role pins.

One end-to-end scenario models `epic_028`: Cursor authentication startup failures → eligible return → reviewed provider/model change → backlog refresh → Codex activation, with the archived Cursor checkpoint demonstrably ignored. Add refusal journeys for approved planning and child/review work.

Depends on Feature 2.

## Verification strategy

Favor a small number of stateful integration and end-to-end tests over mock-heavy unit coverage:

- Table-driven evaluator tests define the eligibility contract and stable reason codes.
- Lifecycle integration tests use real persisted state plus controllable failure injection to validate replay and idempotency at every journal boundary.
- Git/worktree integration tests prove clean preservation and dirty/unmerged refusal without touching trunk.
- A single full journey validates missing credentials, return, reviewed edit, refresh, and fresh activation.
- Existing cancellation, backlog editing, activation, and audit suites remain regression gates where behavior is shared.

## Rollout and observability

Ship behind a capability flag if lifecycle controls use flags today; otherwise authorization plus strict eligibility is the gate. Record transition ID, Epic ID, actor, prior/new state, source revision, step progress, refusal codes, and deduplicated audit outcome. Never log provider credentials or transcript content.

Operators must be able to distinguish: ineligible, quiescing, transition pending/recovering, completed, and failed with retry safe. A recovery scan resumes incomplete journals on startup.

## Open questions

None blocking. Feature planning should bind the contracts above to existing module names and persistence primitives without widening scope.

## Decision log

- 2026-10-31 · Human · Brief approved through merge request review.
- 2026-11-01 · Epic Manager · Treat Return to backlog as a narrow, human-only lifecycle correction with a shared fail-closed eligibility contract.
- 2026-11-01 · Epic Manager · Use a durable replay-safe transition journal plus lifecycle lock and quiescence; retries converge on one result and one audit event.
- 2026-11-01 · Epic Manager · Preserve the former active run as evidence, restore the approved source brief, and require a new activation identity so stale provider pins cannot resume.

- `dec_001` · 2026-11-01 · Epic Manager · **Lifecycle scope**
  Chose Treat Return to backlog as a narrow, human-only lifecycle correction with a shared fail-closed eligibility contract..
  Rationale: The core need is to repair an activation that produced no substantive work; broader rollback semantics would risk reviewed work and expand scope.
  Honors: Success criteria 1; human-only control; refusal explanations; no cancellation or in-place provider edits..

- `dec_002` · 2026-11-01 · Epic Manager · **Transition semantics**
  Chose Use quiescence, a per-Epic lifecycle lock, and a durable replay-safe transition journal with deduplicated audit emission..
  Rationale: A multi-step filesystem and board transition must survive concurrency, retries, and process restarts without duplicate state or data loss.
  Honors: Success criteria 2; restart safety; idempotency; one audit event; operator trunk protection..

- `dec_003` · 2026-11-01 · Epic Manager · **Reactivation boundary**
  Chose Preserve the former active run as evidence, restore the approved source brief, and require a fresh activation identity and role pins..
  Rationale: The reviewed backlog flow must remain authoritative, while stale checkpoints must not reselect the failed provider.
  Honors: Success criteria 3 and 4; preserved history; MR-backed edits; fresh Codex reactivation..
## Amendment log

_(none)_
