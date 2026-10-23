---
id: epic_015
title: Approve plan is not available before manager and architect sign off
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
# Approve plan only after manager and architect sign-off

## Intent

Prevent a human from approving an epic plan before the Epic Manager and Epic Architect have both declared the current plan ready. Make the planning state obvious so reviewers know whether to wait or review.

The server-owned planning-readiness state is authoritative. The UI reflects that state and cannot bypass it.

## Success criteria

- Immediately after epic-team activation, **Approve plan** is visible but disabled.
- The Epic Manager and Epic Architect each sign off independently on the current plan revision.
- A role cannot sign off while the epic has unresolved open questions.
- **Approve plan** becomes enabled only when both required role sign-offs exist for the current plan revision and no unresolved open questions remain.
- Approval is rejected by the server when those conditions are not met, including for stale clients or direct requests.
- Any material plan revision after a sign-off invalidates the prior sign-offs and returns the epic to planning.
- While readiness conditions are unmet, the plan entry point shows **Planning in progress** with a lightweight activity indicator.
- When readiness conditions are met, the plan entry point shows **Ready for review** with a distinct success treatment; the plan remains viewable throughout.
- Existing already-approved plans remain approved and are not retroactively blocked.

## Scope

### In scope

- A single computed readiness contract for epic-plan approval.
- Independent manager and architect sign-offs tied to the current plan revision.
- Rejection of sign-off when unresolved open questions exist.
- Invalidation of stale sign-offs after a material plan edit.
- Server-side enforcement of the approval precondition.
- Disabled/enabled approval affordance and planning/readiness status in the existing epic UI.
- Focused tests at the state-transition/API boundary plus one UI integration path.

### Out of scope

- A general-purpose approval engine for other work-item types.
- New notification, assignment, or reminder systems.
- Presence detection or claims that an agent is currently executing; the activity indicator represents workflow state only.
- Redesign of the plan viewer or approval surface.
- Retroactive migration of completed or already-approved epics.

## User flow

1. A human activates the epic team.
2. The epic enters planning with no valid sign-offs. The plan can be viewed, but approval is disabled and labeled **Planning in progress**.
3. The manager and architect refine the plan and resolve all open questions.
4. Each role signs off on the same current plan revision.
5. The state becomes **Ready for review** and **Approve plan** becomes enabled.
6. If the plan materially changes before human approval, both sign-offs become stale, approval is disabled, and the state returns to **Planning in progress**.
7. Human approval succeeds only if the server re-evaluates the readiness invariant at request time.

## Macro-architecture

### Domain contract

Expose one authoritative derived state for an active epic:

- `planning`: one or more readiness conditions are unmet.
- `ready_for_review`: both required roles signed the current revision and there are no unresolved open questions.
- `approved`: existing terminal plan-approval state.

A sign-off records the role and plan revision. Readiness is computed rather than independently toggled, preventing UI and backend drift.

### Command rules

- **Sign off:** permitted only to the corresponding required role, only against the current revision, and only when unresolved open questions are absent.
- **Edit plan:** creates a new material revision; prior sign-offs no longer satisfy readiness.
- **Approve plan:** permitted only when the derived state is `ready_for_review`; otherwise return the existing domain-validation error shape.
- Repeated sign-off for the same role and revision is idempotent.

### Read model and UI

The existing epic detail/plan read model supplies:

- derived planning state;
- which required roles have valid sign-offs;
- whether approval is allowed;
- a stable disabled reason when approval is not allowed.

The existing plan entry point renders the state. The approval action uses the server-provided capability but still relies on server enforcement.

## Cross-module constraints

- Authorization remains role-based; a client cannot submit sign-off on behalf of another role.
- Sign-offs are revision-bound. Use the repository's canonical plan revision identifier rather than introducing a parallel counter.
- “Open questions” must use the board's canonical unresolved-question representation. Do not infer readiness from arbitrary prose outside that representation.
- State transitions and sign-offs must be persisted so page refreshes and concurrent clients agree.
- Approval validation and readiness computation share the same domain predicate.
- Accessibility: disabled state is semantic, status text does not rely on color alone, and the activity indicator respects reduced-motion preferences.
- Preserve existing API error conventions and approved-plan behavior.

## Core dependencies

- Existing epic activation and plan-approval commands.
- Canonical plan revision/version metadata.
- Canonical unresolved-open-question state.
- Existing epic detail/plan read model and approval control.

If no canonical machine-readable unresolved-question state exists, the implementation must add the smallest explicit field within the planning domain; markdown text parsing is not acceptable.

## Feature breakdown

1. **Authoritative epic-plan readiness and approval gate**
   - Persist revision-bound manager and architect sign-offs.
   - Compute readiness from sign-offs, current revision, and unresolved questions.
   - Enforce sign-off and approval commands server-side.
   - Invalidate readiness through revision mismatch.
   - Cover initial activation, partial/full sign-off, open-question rejection, stale revision, idempotency, and already-approved compatibility at the domain/API boundary.

2. **Planning readiness in the epic UI** *(depends on feature 1)*
   - Consume the readiness/capability read model.
   - Disable **Approve plan** with an explanatory reason until ready.
   - Show **Planning in progress** and a reduced-motion-safe indicator while blocked.
   - Show **Ready for review** with a distinct non-color-only treatment when ready.
   - Verify the primary activation-to-ready UI transition and stale-client error handling.

## Acceptance scenarios

- **New activation:** given a newly activated epic, approval is disabled and a direct approval request is rejected.
- **One sign-off:** given only manager or architect sign-off, approval remains disabled.
- **Open questions:** given unresolved questions, either role's sign-off request is rejected with an actionable reason.
- **Both sign-offs:** given no unresolved questions and both roles signed the current revision, the UI shows ready and approval is accepted.
- **Revision changed:** given both roles signed revision A, when the plan becomes revision B, approval is disabled until both sign revision B.
- **Concurrent/stale client:** given readiness changed after page load, the server's current evaluation wins and the UI refreshes the state after rejection.
- **Existing approved epic:** given a plan approved before this capability ships, it remains approved.

## Delivery and test strategy

Prefer a small set of high-signal tests:

- Domain/API transition table for the readiness invariant and command authorization.
- Integration test proving activation → two sign-offs → enabled approval → approval.
- One UI test for disabled reason and status transition.
- No redundant unit tests for selectors already exercised by those flows.

Roll out as one behavior change. If schema evolution is required, use an additive migration with a safe empty-sign-off default for active, unapproved epics.

## Open questions

_None. Implementation discovery may choose storage and endpoint names but must preserve the contracts above._

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-10-23 · Epic Manager · Approval readiness is server-authoritative and requires both required roles to sign the current plan revision with no unresolved open questions.
- 2026-10-23 · Epic Manager · Material plan revisions invalidate readiness through revision-bound sign-offs.
- 2026-10-23 · Epic Manager · “Planning in progress” describes workflow state, not live agent presence; a ready state receives the distinct review treatment.
- 2026-10-23 · Epic Manager · Scope is split into an authoritative domain/API gate followed by its UI presentation.
- 2026-10-23 · Epic Manager · Existing approved epics remain approved; active unapproved epics default to no valid sign-offs.

- `dec_001` · 2026-10-23 · Epic Manager · **Plan readiness invariant**
  Chose Treat readiness as a server-authoritative derived state requiring valid manager and architect sign-offs on the current plan revision and no unresolved open questions..
  Rationale: A single predicate prevents UI-only bypasses and keeps sign-off, read-model capability, and approval validation consistent.
  Honors: Success criteria: both roles must sign off, open questions block sign-off, and approval is unavailable until ready..

- `dec_002` · 2026-10-23 · Epic Manager · **Sign-off invalidation**
  Chose Bind sign-offs to the canonical plan revision so material plan edits make prior sign-offs stale..
  Rationale: Human approval must apply to the plan the two roles actually reviewed, without introducing a second version counter.
  Honors: The core requirement that manager and architect sign off on the plan before approval..

- `dec_003` · 2026-10-23 · Epic Manager · **Planning status semantics**
  Chose Use Planning in progress for unmet readiness and Ready for review for met readiness; do not implement live agent presence..
  Rationale: This provides the requested wait/review signal without adding unreliable presence infrastructure.
  Honors: The requested churning indicator and distinct feedback-ready treatment..
## Amendment log

_(none)_
