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

Shorten epic lead time by allowing the next approved feature in a linear dependency stack to start after its single ordered predecessor is complete, even when that predecessor's pull request has not merged. The resulting pull requests form a linear stack and remain reviewable and mergeable in feature order.

### Success criteria

- An approved feature is dispatched when its single declared predecessor is either merged or complete and safe to stack.
- A stacked feature pull request targets its completed-but-unmerged predecessor's branch.
- A feature cannot enter the completed state until a durable feature-to-pull-request link has been populated.
- An incomplete, failed, blocked, unapproved, or unresolved predecessor still prevents downstream dispatch.
- After the predecessor merges, GitHub's native retargeting moves the downstream pull request to the epic's normal integration/base branch; reconciliation verifies the result without duplicate dispatch or pull requests.
- Existing behavior remains unchanged for first features and features whose predecessors are already merged.
- Dependency fan-in is outside this epic's stacking scope and fails closed with a visible unsupported-topology reason.

## Macro-architecture

Use the existing feature dependency graph as the stack definition; do not introduce a second ordering model. This epic supports only linear stacks.

The scheduler/dispatcher evaluates each approved feature against its single declared predecessor. A merged predecessor satisfies the dependency normally. A complete but unmerged predecessor also satisfies dispatch eligibility, while supplying its head branch as the downstream pull request base. Any other predecessor state remains blocking. Features with dependency fan-in are not eligible for stacked dispatch in this slice.

Persist the feature-to-pull-request link in project state before allowing a feature to become complete. Persist or derive the selected upstream feature and base branch through the existing durable dispatch/feature state so retries are deterministic. At pull-request creation, the GitHub adapter uses the selected base. When an upstream pull request merges, reconciliation verifies GitHub's native retargeting moved the downstream pull request to the epic's integration/base branch and clearly reports stale state. If native retargeting is not available or reliable, explicit retargeting is deferred to a follow-up feature.

## Cross-module constraints

- The feature dependency graph is authoritative for both dispatch order and pull request stacking.
- This epic supports only linear stacks: a stacked feature has at most one direct predecessor. Dependency fan-in fails closed with a visible unsupported-topology reason.
- Stacking is permitted only after a predecessor reaches the existing completed state; it must not relax approval, failure, cancellation, or blocking gates.
- Completion requires a durable feature-to-pull-request link; missing or unresolvable pull-request identity fails closed.
- Scheduler and reconciliation operations must remain idempotent under retries and restarts.
- Keep provider-specific pull request operations behind the existing GitHub/integration boundary.
- Assume GitHub native base retargeting after predecessor merge; this slice verifies and diagnoses the result but does not implement explicit retargeting.
- Preserve current behavior for non-stacked work and avoid introducing a custom merge queue.

## Core dependencies

- Existing feature dependency and approval state.
- Existing scheduler/dispatcher eligibility checks.
- Durable project-state mapping from features to pull requests.
- Existing worktree/branch identity for completed features.
- Existing pull request creation and reconciliation integration with GitHub.
- Epic integration/base branch resolution.

## Feature breakdown

1. **feat_007_001 — Dispatch and verify native retargeting for linear stacked feature PRs**
   - Deliver the complete vertical slice: completion-gated feature-to-pull-request linkage, eligibility for a single complete-but-unmerged predecessor, deterministic base selection, pull request creation, post-merge verification of native retargeting, diagnostics, and focused integration coverage.
   - No prerequisite feature. This single feature is the smallest independently useful release; splitting scheduler and pull-request behavior would create a nonfunctional intermediate state.
   - Explicit provider-side retargeting is excluded; mint a follow-up feature only if implementation evidence shows native retargeting is unavailable or unreliable.

## Delivery sequence

1. Map the existing dependency-state, feature-to-pull-request linkage, and pull-request lifecycle boundaries.
2. Enforce durable pull-request linkage before feature completion.
3. Implement linear-stack eligibility and deterministic base selection.
4. Pass the selected base through pull-request creation without changing non-stacked behavior.
5. Verify native downstream base retargeting after upstream merges and surface stale state.
6. Verify the two-feature path, a three-feature linear chain, unsupported fan-in, blocking states, missing pull-request linkage, and retry idempotency.

## Open questions

_(none)_

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

- `dec_004` · 2026-10-22 · Epic Architect · **Architecture**
  Chose Require a uniquely nearest completed-but-unmerged predecessor for stacking; fail closed on incomparable unmerged dependency fan-in..
  Rationale: A pull request has exactly one base branch. Selecting arbitrarily among incomparable predecessors would make the declared dependency graph and the actual code ancestry disagree.
  Honors: The existing dependency graph as the sole ordering model, deterministic retries, visible diagnostics, and fail-closed safety..

- `dec_005` · 2026-10-22 · Epic Manager · **Provider behavior**
  Chose Assume GitHub native base retargeting after predecessor merge; verify and diagnose it in this epic, and defer explicit retargeting to a follow-up feature if implementation evidence disproves the assumption. In reply to: cmt_001.
  Rationale: This keeps the first release to the smallest useful slice while preserving a clear fallback if the provider contract is insufficient.
  Honors: The human's stated assumption, focused scope, visible failure behavior, and avoidance of speculative provider work..

- `dec_006` · 2026-10-22 · Epic Manager · **Lifecycle integrity**
  Chose Require a durable feature-to-pull-request link in project state before a feature can enter the completed state. In reply to: cmt_001.
  Rationale: Downstream stacking depends on resolving the completed predecessor's pull request and branch deterministically; completion without that identity would create an unsafe, unrecoverable gap.
  Honors: The human's tracking requirement, fail-closed safety, deterministic retries, and artifact-driven lifecycle state..

- `dec_007` · 2026-10-22 · Epic Manager · **Scope**
  Chose Limit stacked dispatch in this epic to linear dependency chains; dependency fan-in is unsupported and fails closed with a visible topology reason. This supersedes dec_004's unique-nearest fan-in handling for this epic. In reply to: cmt_001.
  Rationale: A pull request has one base, and linear-only support meets the core lead-time goal without adding graph-selection behavior that the requested scope does not need.
  Honors: The human's scope direction, the existing dependency graph, deterministic behavior, and the smallest complete vertical slice..
## Amendment log

_(none)_
