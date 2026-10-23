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
plan_approved_at: '2026-10-23T03:13:51.808473+00:00'
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
- `dispatch_feature` already enforces the gates under a process lock: open status, `unmet_deps`, `not_approved`, `feature_awaiting_merge`, and sibling block (also reported as `feature_awaiting_merge`). After those gates it can still refuse through `ensure_feature_dispatch_selection` (stacked base unavailable) and the blocking-comment gate. Once a feature moves to active, a second dispatch fails with `bad_state`, so repeated approvals cannot dispatch twice.
- `reconcile_approval_dispatch` only tries features listed in `compute_boss_view().dispatchable_features` (`cascade/boss/view.py`). That list is a second copy of the gates with slightly different checks (`feature_dependency_ready`, `feature_merge_gated`, a `1_backlog` path check). Reconcile then applies a third check: the parent epic must be active.
- `serialize.py` exposes `approved` and `approved_at` on feature rows. It does not expose why a feature is still in backlog.
- `war_room.js` has "Approve plan" and "Approved" controls for epics, but feature rows have no approval control.

What this epic adds:

1. **A read-only readiness predicate** (feat_020_001). The gate logic from all three sites (`_dispatch_feature`, the boss-view feature filter, and reconcile's active-epic check) moves into one pure function. The dispatcher, the boss view, reconcile, and the board serializer all call it. It also covers the post-gate refusals through their read-only forms (`plan_feature_dispatch`, `refusal_if_blocked`). Feature rows gain `readiness: {approved, blockers[]}`. The predicate has no side effects: it never calls `ensure_feature_dispatch_selection`, writes, emits events, or takes the dispatch lock. `DispatchResult.reason` values stay the same.
2. **A War Room control** (feat_020_002). Feature rows show an "Awaiting feature approval" status and an "Approve feature" button that calls the existing `/api/approve_feature`, with pending, success, and error feedback. After approval, rows show the remaining blockers. One integration test covers the full late-mint path.

Data flow: an operator clicks the button, which POSTs `/api/approve_feature`. The handler persists `approved_at`, then runs `advance_work` → `reconcile_approval_dispatch` → `dispatch_feature` (the canonical gates). On success the kickoff is queued in the background and the HTTP response returns. On the next board refresh, the readiness predicate shows the feature as active, or still in backlog with its real blocker.

## Cross-module constraints

Preserve per-feature approved_at as durable authority and preserve the current snapshot semantics for epic-plan approval. Only a human may grant the missing approval. Reuse /api/approve_feature and canonical dispatch/reconciliation rather than adding a second approval store or bypass. Coordinate labels/readiness presentation with epic_015, but do not make this work depend on auto-approval or broaden epic_015's planner sign-off scope. Re-approval and refreshes must not duplicate worktrees, queue events, or model turns.

Rules added during planning:

- Displayed blockers and actual dispatch decisions must come from the same predicate. A UI-only copy of the gate logic is not allowed. This includes the boss-view filter that reconcile relies on.
- The refactor must not loosen any gate. Where the current copies differ, the predicate must be at least as strict as their conjunction.
- The approval action stays on the loopback War Room HTTP surface. No agent or MCP tool gains an approve capability.
- Feature labels use feature-row vocabulary ("Awaiting feature approval", "Approve feature"). They must not reuse or restyle epic_015's epic-level "Approve plan" controls.

## Core dependencies

- `cascade/approvals.py` (`approve_feature`, `feature_approved`): reused, not modified.
- `cascade/watchdog/dispatch.py` (`dispatch_feature` gates): refactored to call the shared readiness predicate, with no behavior change.
- `cascade/boss/view.py` (`compute_boss_view` feature filter): refactored to call the shared predicate, with no behavior change.
- `cascade/stacked_dispatch.py` (`plan_feature_dispatch`, `read_feature_dispatch_selection`) and `cascade/comments/gate.py` (`refusal_if_blocked`): reused read-only by the predicate.
- `cascade/automation.py` (`reconcile_approval_dispatch`): reused. Its active-parent-epic check is reported as the `epic_inactive` blocker.
- `cascade/workspace/kickoff.py` (`deferred_kickoffs`, `kickoff_turn`): reused for background kickoff.
- `cascade/war_room/serialize.py` and `static/war_room.js`: extended.
- epic_015 (active): presentation coordination only, with no code dependency.

## Feature breakdown

1. **feat_020_001: Expose side-effect-free feature readiness and blockers.** No dependencies. A behavior-preserving extraction of the dispatch gates plus `readiness` on feature rows. It ships alone because it is useful on its own (it removes the "appears stuck" ambiguity in API payloads) and keeps the dispatch refactor reviewable.
2. **feat_020_002: War Room feature approval control with end-to-end late-mint test.** Depends on feat_020_001. Adds the UI button, status text, and feedback, plus the single integration test required by the success criteria, including the no-duplicate-dispatch, no-inline-model-turn, and blocked-sibling checks.

The work is a strict sequence; there is no parallelism worth the coordination cost at this size.

## Open questions

- Resolved: which implementation risks should be settled before the first feature starts? See the decision log. The risks are readiness-vs-dispatch drift (across all three gate sites), the side-effecting `ensure_feature_dispatch_selection`, and proof that no model turn runs inline.

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

- `dec_003` · 2026-10-23 · Epic Manager · **Scope**
  Chose Accept two limitations: with automation disabled, approval only persists (manual dispatch still applies); and advance_work stays synchronous within the approval request under the existing 60s APPROVAL_DEADLINE_S. Feature-row labels use their own vocabulary and do not touch epic_015's epic-level Approve plan controls..
  Rationale: Both limitations are current behavior and involve no model turn. Changing them would expand scope without serving the core operator problem. Separate label vocabulary avoids coupling to epic_015 while keeping the presentation consistent.
  Honors: Do not depend on auto-approval or broaden epic_015 scope; snapshot semantics of epic-plan approval unchanged.

- `dec_004` · 2026-10-23 · Epic Architect · **Macro-architecture**
  Chose Sign off on dec_001 through dec_003, with one tightening. The shared readiness predicate replaces all three gate copies on trunk: _dispatch_feature, the compute_boss_view feature filter that reconcile_approval_dispatch iterates over, and reconcile's active-epic check. It also covers the post-gate refusals through their read-only forms (plan_feature_dispatch or read_feature_dispatch_selection, and refusal_if_blocked). New blocker codes are sibling_blocked, dispatch_base_unavailable, and review_threads_blocking. _dispatch_feature maps them back so DispatchResult.reason values are unchanged, and manual dispatch keeps ignoring epic_inactive. Where the current copies differ, the predicate is at least as strict as their conjunction..
  Rationale: Trunk has three gate copies with different checks (boss view uses feature_dependency_ready and feature_merge_gated; dispatch uses _deps_met plus inline merge checks). Two more refusals happen after the gates. If only dispatch and the serializer shared a predicate, the board could show no blockers for a feature that reconcile never selects or that dispatch then refuses, which is the 'appears stuck' failure this epic exists to remove. plan_feature_dispatch and refusal_if_blocked are read-only, so including them keeps the predicate free of side effects.
  Honors: Displayed blockers and actual dispatch decisions come from the same predicate; no gate is loosened; canonical dispatch and reconcile are reused; dispatch behavior and existing tests stay unchanged..
## Amendment log

_(none)_
