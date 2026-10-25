---
id: epic_014
title: Work item cancellation
tier: epic
status: active
parent: null
children:
- feat_014_001
- feat_014_002
- feat_014_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-25'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Work item cancellation

## Intent

Let an operator deliberately stop an epic, feature, or task without pretending it was delivered, while leaving the board and Git workspace consistent and auditable.

Cancellation is a first-class terminal outcome. Active work first enters `cancelling`, performs cleanup and parent feedback, and only then becomes `cancelled`. Failed side effects stay visible and retryable in `cancelling`; the system must not report a clean cancellation prematurely.

## Success criteria

- Backlog and active epics, features, and tasks share one cancellation service and supported command/API contract.
- Each request records actor, time, and a non-empty reason; retries are idempotent.
- Completed/integrated work cannot be relabelled as cancelled.
- Successful active cancellation removes only the local worktree and branch owned by that item through the existing teardown path.
- Dirty or unmerged work requires explicit discard confirmation. Without it, cleanup safely refuses and reports the exact remedy.
- Cancelling a feature or task creates durable feedback on its direct parent and gates new parent dispatch until a user chooses a disposition.
- Interruption or partial failure is safely retryable and successful cancellation leaves no dangling owned worktree/branch.
- Focused end-to-end coverage includes backlog cancellation, active cleanup, dirty-work refusal, child-to-parent disposition, and retry after injected partial failure.

## Scope boundaries

In scope: lifecycle transitions; cancellation metadata; a shared orchestration service; existing branch/worktree teardown integration; structured parent feedback; and three dispositions—continue with reduced scope, replace/replan, or cancel parent.

Out of scope: restoration/archive, bulk cancellation, remote-branch deletion, automatic replacement planning, general pause/resume redesign, and cancellation of completed/integrated work.

## Lifecycle contract

1. Validate target, authorization, and transition. `completed` is rejected; `cancelled` returns the prior result.
2. Capture reason and actor. Active dirty/unmerged work additionally requires explicit discard confirmation.
3. Persist `cancelling` and a stable operation ID before side effects.
4. Resolve Git targets from authoritative item ownership metadata and invoke existing teardown; never use broad globs.
5. For a task or feature, append deduplicated structured feedback to the parent and set a cancellation-review dispatch gate. Epics skip this step.
6. Record an explicit parent disposition. Cancelling the parent starts its own operation and never recursively deletes it.
7. Persist `cancelled` only after every required step succeeds, including cleanup and parent feedback.
8. Retry resumes incomplete steps without duplicating deletion, feedback, or decisions.

A parent with live descendants is not cancellable implicitly. Return their exact IDs and require explicit per-item cancellation so each reason and cleanup outcome remains auditable.

## Parent feedback contract

Feedback includes child ID/tier, reason, actor, timestamps, operation ID, cleanup outcome, and disposition when known. While gated, a parent can be inspected and planned but cannot dispatch new work; existing siblings are not destroyed.

- **Continue with reduced scope:** acknowledge the gap and resume dispatch.
- **Replace/replan:** keep the gate until a revised plan completes the normal approval flow.
- **Cancel parent:** launch a separate explicit cancellation.

The owning board plan/decision trail is the record; chat is not.

## Macro-architecture

- **Lifecycle/domain:** add `cancelling` and `cancelled`, typed metadata, and transition guards.
- **Application service:** coordinate validation, durable checkpoints, cleanup, feedback, disposition, retry, and finalization for every entry point.
- **Git adapter:** reuse owned worktree/branch teardown and return structured per-artifact results, distinguishing retryable failure from safety refusal.
- **Board/event adapter:** append feedback once per operation ID and enforce/release the parent dispatch gate.
- **CLI/API:** require reason; collect explicit destructive confirmation and parent disposition where applicable.
- **Observability:** show current step, exact owned refs/paths, failure, and retry instruction.

This is a small persisted state machine, not a cross-system transaction; checkpoints keep crash recovery honest.

## Cross-module constraints

- The board is authoritative for lifecycle and cancellation metadata.
- Delete only exact, owned local artifacts; protect the repository root, canonical/integration branches, remotes, and unrelated files.
- Never discard dirty/unmerged work without confirmation bound to this operation.
- State checkpoints precede/follow side effects; feedback is deduplicated by operation ID.
- Existing mutation authorization remains in force.
- Extend/wrap existing pause, dispatch-gate, and teardown primitives rather than duplicating them.
- Deploy tolerant readers before enabling writers for new states.
- Prefer service/integration and CLI tests; add focused unit tests only for safety/transition rules not economically covered above.

## Core dependencies

Existing work-item persistence and authorization; status transitions; branch/worktree ownership and teardown; parent/child graph; board plan/decision writes; dispatch gating; and event delivery. No new external service or database.

## Feature breakdown

### feat_014_001 — Cancellation lifecycle and command contract

Add the lifecycle model, persisted operation metadata, transition validation, idempotent shared service, and supported CLI/API inputs.

Acceptance: all tiers handle backlog and active requests; invalid reason, completed target, live descendants, or unauthorized actor causes no destructive side effects; active work checkpoints as `cancelling`; retries reuse one operation; existing views clearly render both new states.

### feat_014_002 — Safe cancellation cleanup

Connect the service to established owned worktree/branch teardown.

Acceptance: success leaves no owned local branch/worktree; protected and unrelated targets cannot be deleted; dirty/unmerged work needs explicit confirmation; failure remains `cancelling` with an actionable exact step and succeeds on safe retry without replaying completed work.

It may proceed once feat_014_001's schema/service contract is stable and need not wait for parent UX.

### feat_014_003 — Parent feedback and replanning gate

Depends on feat_014_001. Add deduplicated feedback, dispatch gating, all three dispositions, normal-plan integration, and end-to-end workflow coverage.

Acceptance: task/feature cancellation creates exactly one direct-parent record and blocks new dispatch; continue resumes; replace/replan uses normal revised-plan approval; cancel parent starts a separate operation; epics perform no parent step; retries duplicate nothing; E2E tests cover cancellation, cleanup, feedback, disposition, and a fault between checkpoints.

## Delivery sequence

1. Ship tolerant readers and feat_014_001's lifecycle/service contract.
2. Build feat_014_002 and feat_014_003 in parallel after the contract stabilizes.
3. Enable an entry point for a tier only when its required teardown safety and parent gate are available.
4. Run the focused E2E matrix and verify no owned artifacts remain after successful active cancellation.

## Risks and mitigations

- Crash across board/Git effects: durable checkpoints and idempotent retry.
- Wrong Git deletion: authoritative ownership, exact targets, protected refs, and discard confirmation.
- Invalid parent scope: mandatory dispatch gate and explicit disposition.
- Unexpected cascade: reject live descendants and require explicit operations.
- Mixed-version readers: tolerant reads precede writes.
- Recovery overbuild: no restore/archive feature; use explicit confirmation and existing Git recovery properties.

## Open questions

_(none blocking; feature discovery may refine command names and storage fields without changing this contract)_

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-25 · Epic Manager · **Lifecycle semantics**
  Chose Use persisted cancelling as the recoverable intermediate state and cancelled only after required cleanup and parent feedback succeed..
  Rationale: Board and Git updates cannot be atomic; explicit checkpoints prevent partial work from being presented as success and make retries safe.
  Honors: Success criteria for cancellation, feedback, and zero Git pollution..

- `dec_002` · 2026-10-25 · Epic Manager · **Parent handling**
  Chose Gate a direct parent after child cancellation and require continue, replace/replan, or cancel-parent disposition; never cascade cancellation implicitly..
  Rationale: A cancelled child can invalidate parent scope, while automatic cascading could destroy unrelated sibling work and obscure user intent.
  Honors: The brief's requirement to give feedback to parent work items and ask what the epic team should do..

- `dec_003` · 2026-10-25 · Epic Manager · **Git safety**
  Chose Reuse exact owned-artifact teardown and require explicit confirmation before discarding dirty or unmerged work..
  Rationale: This removes dangling branches/worktrees while protecting canonical refs, unrelated work, and unacknowledged local changes.
  Honors: The brief's no-Git-pollution outcome and safe destructive-operation constraints..
## Amendment log

_(none)_
