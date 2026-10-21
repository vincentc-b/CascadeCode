---
id: epic_005
title: Lifecycle management
tier: epic
status: active
parent: null
children:
- feat_001
- feat_002
- feat_003
- feat_004
- feat_005
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-21'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Lifecycle management

## Intent

Make approval, dependency dispatch, completion rollup, and merge-request review predictable across the feature and epic lifecycle.

A feature may be approved independently. Epic approval approves every child feature that exists at that time, but implementation dispatch occurs only after the feature is approved, all declared feature dependencies are complete, and the existing merge gate permits another feature to start.

A feature completes only after its tasks are complete and its merge request has merged. An epic completes automatically when all persisted child features are complete. A proposed follow-up blocks that rollup only after it has been accepted and minted as a child feature.

Reviewers can see all open merge requests in a dedicated War Room view and navigate directly to each review.

### Success criteria

- Per-feature and epic-wide approval are durable and dispatch respects approval and `depends_on` completion.
- Feature completion requires completed tasks plus a merged MR.
- Epic completion rolls up automatically from all persisted child features.
- An accepted, persisted follow-up keeps the epic active; an unaccepted suggestion does not.
- War Room provides an Open MRs view backed by the existing durable review registry.
- Lifecycle reconciliation is idempotent after restart.
- One economical sandbox/browser scenario demonstrates the critical lifecycle and review behavior.

## Macro-architecture

Lifecycle decisions remain in existing authoritative services and durable registries:

1. The central dispatch path evaluates durable feature approval, completed dependencies, and the existing one-feature-awaiting-merge constraint.
2. A lifecycle reconciler derives feature completion from task completion plus MR merge state, then derives epic completion from child-feature state; reconciliation is restart-safe and idempotent.
3. A read-only reviews API queries the existing durable review registry.
4. War Room renders Open MRs from that API with direct review links.
5. A disposable system fixture drives public lifecycle entry points to demonstrate the full flow.

No parallel approval, lifecycle, or review store is introduced.

## Cross-module constraints

- Approval is durable state separate from board lifecycle status.
- All implementation entry points pass through one dispatch eligibility check.
- Dependency readiness means every feature in `depends_on` is completed.
- Epic approval applies to children present at approval time; later children require explicit approval.
- Feature completion cannot precede MR merge.
- Epic completion is derived, never manually asserted by this flow.
- Only a follow-up persisted as a child feature participates in completion rollup.
- Review UI and API read from the existing review registry and do not duplicate review state.
- Preserve the current single-feature-awaiting-merge gate.
- Child metadata is authoritative for dispatch; the current titles and dependency edges are aligned with the sequence below.
- Prefer focused integration coverage plus one system/browser scenario; do not create a new test framework if an existing harness suffices.

## Core dependencies

- Existing approval persistence and commands.
- Central dispatch/orchestration and the `depends_on` graph.
- Task completion state and durable merge-request/review registry.
- Lifecycle reconciliation and restart recovery.
- War Room API/frontend routing and the existing browser/system test harness.

## Feature breakdown

1. **feat_001 — Approval and dependency dispatch**
   - Persist per-feature approval and epic-wide approval of current children.
   - Gate central dispatch on approval, completed dependencies, and the existing merge constraint.
2. **feat_002 — Completion rollup and recovery** (depends on feat_001)
   - Complete features after tasks finish and their MR merges.
   - Roll completion up across persisted children and recover idempotently.
3. **feat_003 — Open review registry API** (depends on feat_001 and feat_002)
   - Expose an authoritative read-only open-review model with feature/epic context and direct URLs.
4. **feat_004 — Lifecycle sandbox demonstration** (depends on feat_001 and feat_002)
   - Prove approval, dependency gating, merge ordering, recovery, and rollup through one disposable system scenario.
5. **feat_005 — Open merge requests War Room view** (depends on feat_003 and feat_004)
   - Render Open MRs and usable states, with direct review links.
   - Extend the scenario only enough to prove appearance and disappearance after merge.

## Open questions

- No unresolved epic-level planning questions. Feature planning should reuse existing lifecycle, review, and test abstractions.

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-21 · Epic Team · **Lifecycle approval and dispatch**
  Chose to keep approval as durable state separate from board lifecycle status and enforce approval plus dependency readiness in the central dispatch path.
  Rationale: Approval and status answer different questions; a single dispatch guard prevents bypasses.
  Honors: Per-feature approval, epic-wide approval of current children, dependency-safe dispatch, and restart recovery.

- `dec_002` · 2026-10-21 · Epic Team · **Completion rollup**
  Chose to derive feature completion from completed tasks plus a merged MR, and epic completion from all persisted child-feature states.
  Rationale: Derived state avoids premature or divergent completion and supports idempotent recovery.
  Honors: Automatic feature and epic transitions based on content completion.

- `dec_003` · 2026-10-21 · Epic Team · **Follow-up semantics**
  Chose to make a follow-up completion-blocking only after acceptance and minting as a child feature.
  Rationale: Persisted children provide an auditable boundary without a second backlog state.
  Honors: Keeping an epic active for accepted follow-up work.

- `dec_004` · 2026-10-21 · Epic Team · **Review dashboard**
  Chose to build the Open MRs API and War Room view from the existing durable review registry.
  Rationale: One authoritative registry minimizes synchronization failure.
  Honors: Easy access to open merge requests.

- `dec_005` · 2026-10-21 · Epic Team · **Verification strategy**
  Chose focused lifecycle integration tests and one browser/system flow over broad redundant unit coverage.
  Rationale: This covers high-value boundaries and recovery with lower maintenance cost.
  Honors: Pragmatic validation and a Playwright-style demonstration.

- `dec_006` · 2026-10-21 · Epic Team · **Feature sequencing after concurrent mint**
  Chose Retain the five minted children but remove overlap: feat_003 owns the read-only review API, feat_004 owns the lifecycle sandbox scenario, and feat_005 owns the War Room UI; feat_005 waits for both API and sandbox..
  Rationale: Concurrent planning minted two additional children after the original three-feature breakdown. Giving each a narrow, independently verifiable boundary avoids duplicate implementation and preserves an ordered smallest-coherent delivery without inventing unrelated scope.
  Honors: The requested sandbox demonstration, Open MRs dashboard, dependency-safe sequencing, and frugal high-signal testing..

- `dec_007` · 2026-10-21 · Epic Architect · **Feature metadata as dispatch contract**
  Chose Treat child feature metadata as authoritative for dispatch and block approval of feat_004 and feat_005 until their titles and dependency edges match the epic sequence..
  Rationale: Feature-body prose cannot enforce orchestration order. The current metadata omits feat_002 from feat_004 and feat_003 from feat_005, which could bypass required lifecycle/API prerequisites.
  Honors: Dependency-safe dispatch, artifact-driven alignment, and the smallest coherent delivery sequence..

- `dec_008` · 2026-10-21 · Epic Manager · **Metadata reconciliation**
  Chose Treat the corrected child titles and dependency edges as authoritative and clear the pre-approval dispatch blocker..
  Rationale: Board metadata now matches the epic sequence: feat_004 depends on feat_001 and feat_002, while feat_005 depends on feat_003 and feat_004; the stale titles for feat_003 through feat_005 are also aligned.
  Honors: Dependency-safe dispatch, artifact-driven alignment, and the smallest coherent five-feature plan..

- `dec_009` · 2026-10-21 · Epic Architect · **Architecture readiness after metadata reconciliation**
  Chose Accept the reconciled five-feature architecture and dependency graph as ready for sequenced delivery..
  Rationale: Authoritative child metadata now matches the epic contract: feat_002 follows feat_001; feat_003 and feat_004 follow the lifecycle foundation; feat_005 follows both the review API and lifecycle demonstration. The slices remain non-overlapping and use focused integration coverage plus one system flow.
  Honors: Dependency-safe dispatch, artifact-driven alignment, durable lifecycle state, one authoritative review registry, and frugal high-signal verification..
## Amendment log

_(none)_
