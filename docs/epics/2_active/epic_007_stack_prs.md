---
id: epic_007
title: Stack PRs
tier: epic
status: active
parent: null
children:
- feat_007_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Stack PRs

## Intent

Shorten epic lead time by allowing the next approved feature to start after its ordered predecessor is complete, even when that predecessor's pull request has not merged. The resulting pull requests form a dependency stack and remain reviewable and mergeable in feature order.

### Success criteria

- An approved feature is dispatched when every declared predecessor is either merged or complete and safe to stack.
- A stacked feature pull request targets the nearest unmerged predecessor's branch.
- An incomplete, failed, blocked, or unapproved predecessor still prevents downstream dispatch.
- After the predecessor merges, the downstream pull request targets the epic's normal integration/base branch without duplicate dispatch or pull requests.
- Existing behavior remains unchanged for first features and features whose predecessors are already merged.

## Macro-architecture

Use the existing feature dependency graph as the stack definition; do not introduce a second ordering model.

The scheduler/dispatcher evaluates each approved feature against its declared predecessors. A merged predecessor satisfies the dependency normally. A complete but unmerged predecessor also satisfies dispatch eligibility, while supplying its head branch as the downstream pull request base. Any other predecessor state remains blocking.

Persist or derive the selected upstream feature and base branch through the existing durable dispatch/feature state so retries are deterministic. At pull-request creation, the GitHub adapter uses the selected base. When an upstream pull request merges, normal reconciliation verifies that the downstream base has moved to the epic's integration/base branch; accept GitHub's native retargeting when correct and repair or clearly report stale state otherwise.

## Cross-module constraints

- The feature dependency graph is authoritative for both dispatch order and pull request stacking.
- Stacking is permitted only after a predecessor reaches the existing completed state; it must not relax approval, failure, cancellation, or blocking gates.
- Choose the nearest unmerged predecessor in a chain; never skip an incomplete predecessor.
- Scheduler and reconciliation operations must remain idempotent under retries and restarts.
- Keep provider-specific pull request operations behind the existing GitHub/integration boundary.
- Preserve current behavior for non-stacked work and avoid introducing a custom merge queue.

## Core dependencies

- Existing feature dependency and approval state.
- Existing scheduler/dispatcher eligibility checks.
- Existing worktree/branch identity for completed features.
- Existing pull request creation and reconciliation integration with GitHub.
- Epic integration/base branch resolution.

## Feature breakdown

1. **feat_007_001 — Dispatch and retarget stacked feature PRs**
   - Deliver the complete vertical slice: eligibility for complete-but-unmerged predecessors, deterministic base selection, pull request creation, post-merge reconciliation, diagnostics, and focused integration coverage.
   - No prerequisite feature. This single feature is the smallest independently useful release; splitting scheduler and pull-request behavior would create a nonfunctional intermediate state.

## Delivery sequence

1. Map the existing dependency-state and pull-request lifecycle boundaries.
2. Implement stack-aware eligibility and deterministic base selection.
3. Pass the selected base through pull-request creation without changing non-stacked behavior.
4. Reconcile downstream bases after upstream merges.
5. Verify the two-feature path, a three-feature chain, blocking states, and retry idempotency.

## Open questions

- Does the current GitHub integration observe native base retargeting after an upstream merge, or must reconciliation explicitly update the downstream pull request? Resolve during implementation against the adapter's observed contract; no separate discovery feature is warranted.
- If a completed predecessor's branch or pull request cannot be resolved, fail closed with a visible blocked reason rather than falling back to the epic base.

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-22 · Epic Manager · **Safety**
  Chose Permit stacking only from a completed-but-unmerged predecessor and fail closed when its branch or pull request cannot be resolved..
  Rationale: This captures the lead-time benefit without allowing downstream work to build on unstable or ambiguous state.
  Honors: Existing approval and dependency gates, idempotent dispatch, and system reliability..

- `dec_002` · 2026-10-22 · Epic Manager · **Architecture**
  Chose Use the existing declared feature dependency graph as the sole definition of pull request stack order..
  Rationale: A second ordering model would create drift and additional lifecycle state without adding user value.
  Honors: The approved brief's sequential feature semantics and the requirement that downstream work follow its priors..

- `dec_003` · 2026-10-22 · Epic Manager · **Scope**
  Chose Deliver stack-aware dispatch, pull request base selection, and post-merge reconciliation as one vertical-slice feature..
  Rationale: None of these parts is independently useful; a single feature is the smallest shippable slice and avoids coordination overhead.
  Honors: The core outcome of dispatching approved downstream features before predecessor merge while keeping their pull requests correctly based..
## Amendment log

_(none)_
