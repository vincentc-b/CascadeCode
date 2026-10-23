---
id: epic_020
title: Make late-minted features visibly approvable
tier: epic
status: active
parent: null
children:
- feat_020_001
- feat_020_002
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
# Make late-minted features visibly approvable

## Intent

A feature minted after its epic plan was approved correctly remains unapproved, but the War Room provides no feature-level approval control or clear waiting reason. Operators therefore see a dependency-ready backlog feature that appears stuck and must use an undocumented API to continue. Provide a complete human approval path for these features without weakening the existing approval boundary.

### Success criteria

- An unapproved backlog feature has a clear "Awaiting feature approval" state and a human-only approval action in the War Room.
- The action uses the existing durable, idempotent feature approval operation and shows pending, success, and actionable failure feedback.
- After approval, an otherwise eligible feature is scheduled automatically; an ineligible feature remains in backlog with its actual dependency, sibling, review, or merge blocker visible.
- The approval HTTP request persists approval and returns without waiting for a feature-planning model turn; kickoff runs through the normal deferred/background path.
- A browser/API integration test covers an epic approved with its initial children, a feature minted afterward, the visible approval action, one approval, and exactly one dispatch.
- Existing behavior remains explicit: approving an epic plan approves only the children present at that moment, and later features are never silently approved.

## Macro-architecture

Most of the backend path already exists. This epic adds visibility and a UI control; it does not add a new approval mechanism.

What exists today (verified on trunk):

- `cascade/approvals.py::approve_feature`: sets `approved_at` once (idempotent; returns `newly_approved`), then calls `advance_work`, which runs `reconcile_approval_dispatch` when automation is enabled.
- `POST /api/approve_feature` in `cascade/war_room/server.py`: errors map to 409. Every POST runs inside `deferred_kickoffs()`, so `dispatch_feature` → `kickoff_turn` queues the feature-planning model turn in the background instead of running it on the request thread.
- `dispatch_feature` already enforces the gates under a process lock: open status, `unmet_deps`, `not_approved`, `feature_awaiting_merge`, and sibling block. Once a feature moves to active, a second dispatch fails with `bad_state`, so repeated approvals cannot dispatch twice.
- `serialize.py` exposes `approved` and `approved_at` on feature rows. It does not expose why a feature is still in backlog.
- `war_room.js` has "Approve plan" and "Approved" controls for epics, but feature rows have no approval control.

What this epic adds:

1. **A read-only readiness predicate** (feat_020_001). The gate logic moves out of `_dispatch_feature` into one pure function that both `dispatch_feature` and the board serializer call. Feature rows gain `readiness: {approved, blockers[]}`. The predicate has no side effects: it never calls `ensure_feature_dispatch_selection`, writes, emits events, or takes the dispatch lock.
2. **A War Room control** (feat_020_002). Feature rows show an "Awaiting feature approval" status and an "Approve feature" button that calls the existing `/api/approve_feature`, with pending, success, and error feedback. After approval, rows show the remaining blockers. One integration test covers the full late-mint path.

Data flow: an operator clicks the button, which POSTs `/api/approve_feature`. The handler persists `approved_at`, then runs `advance_work` → `reconcile_approval_dispatch` → `dispatch_feature` (the canonical gates). On success the kickoff is queued in the background and the HTTP response returns. On the next board refresh, the readiness predicate shows the feature as active, or still in backlog with its real blocker.

## Cross-module constraints

Preserve per-feature approved_at as durable authority and preserve the current snapshot semantics for epic-plan approval. Only a human may grant the missing approval. Reuse /api/approve_feature and canonical dispatch/reconciliation rather than adding a second approval store or bypass. Coordinate labels/readiness presentation with epic_015, but do not make this work depend on auto-approval or broaden epic_015's planner sign-off scope. Re-approval and refreshes must not duplicate worktrees, queue events, or model turns.

Rules added during planning:

- Displayed blockers and actual dispatch decisions must come from the same predicate. A UI-only copy of the gate logic is not allowed.
- The approval action stays on the loopback War Room HTTP surface. No agent or MCP tool gains an approve capability.
- Feature labels use feature-row vocabulary ("Awaiting feature approval", "Approve feature"). They must not reuse or restyle epic_015's epic-level "Approve plan" controls.

## Core dependencies

- `cascade/approvals.py` (`approve_feature`, `feature_approved`): reused, not modified.
- `cascade/watchdog/dispatch.py` (`dispatch_feature` gates): refactored to call the shared readiness predicate, with no behavior change.
- `cascade/automation.py` (`reconcile_approval_dispatch`): reused. Its active-parent-epic check is reported as the `epic_inactive` blocker.
- `cascade/workspace/kickoff.py` (`deferred_kickoffs`, `kickoff_turn`): reused for background kickoff.
- `cascade/war_room/serialize.py` and `static/war_room.js`: extended.
- epic_015 (active): presentation coordination only, with no code dependency.

## Feature breakdown

1. **feat_020_001: Expose side-effect-free feature readiness and blockers.** No dependencies. A behavior-preserving extraction of the dispatch gates plus `readiness` on feature rows. It ships alone because it is useful on its own (it removes the "appears stuck" ambiguity in API payloads) and keeps the dispatch refactor reviewable.
2. **feat_020_002: War Room feature approval control with end-to-end late-mint test.** Depends on feat_020_001. Adds the UI button, status text, and feedback, plus the single integration test required by the success criteria, including the no-duplicate-dispatch, no-inline-model-turn, and blocked-sibling checks.

The work is a strict sequence; there is no parallelism worth the coordination cost at this size.

## Open questions

- Resolved: which implementation risks should be settled before the first feature starts? See the decision log. The risks are readiness-vs-dispatch drift, the side-effecting `ensure_feature_dispatch_selection`, and proof that no model turn runs inline.

## Known limitations (accepted)

- With automation disabled, approval persists but nothing is scheduled automatically (this is current `_maybe_advance_after_approval` behavior). The row then shows no blockers, and the existing manual dispatch path applies. This epic does not change that.
- `advance_work` still runs synchronously within the approval request (brief sync and reconciliation, but no model turn). The existing 60s `APPROVAL_DEADLINE_S` covers it. Moving it fully off-thread is out of scope unless the integration test shows a real latency problem.

## Decision log

- 2026-10-23 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-23 · Epic Manager · **Macro-architecture**
  Chose Two sequential features: feat_020_001 (pure readiness predicate shared by dispatch_feature and the board serializer) then feat_020_002 (War Room approve control plus one end-to-end late-mint integration test). Do not add a new endpoint, approval store, or agent-facing approve tool..
  Rationale: approve_feature, /api/approve_feature, idempotent approved_at, deferred_kickoffs on all POSTs, and dispatch gates already exist on trunk. The gap is visibility and a UI control. Sharing a single predicate stops the displayed blocker from drifting away from the real dispatch decision.
  Honors: Reuse /api/approve_feature and canonical dispatch; per-feature approved_at stays authoritative; human-only approval; no duplicate dispatch.

- `dec_002` · 2026-10-23 · Epic Manager · **Open questions**
  Chose Risks to settle before feat_020_001 starts: (1) the readiness predicate must exclude ensure_feature_dispatch_selection and every write, event, or lock; (2) dispatch_feature must call the same predicate, with existing dispatch tests as the regression guard; (3) the feat_020_002 integration test must assert that the kickoff is queued in the background, not run on the request thread, and that a second approve or refresh adds no dispatch, worktree, queue event, or kickoff..
  Rationale: These are the only ways this epic could weaken an existing guarantee: a side-effecting read, UI/dispatch drift, or a blocking or duplicated model turn. Everything else is additive.
  Honors: Re-approval and refreshes must not duplicate worktrees, queue events, or model turns; approval request returns without waiting for a model turn.
## Amendment log

_(none)_
