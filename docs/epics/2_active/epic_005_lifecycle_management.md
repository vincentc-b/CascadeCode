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

Reviewers can see all open merge requests in a dedicated War Room dashboard and navigate directly to each review.

### Success criteria

- Per-feature and epic-wide approval are durable and dispatch respects both approval and `depends_on` completion.
- Feature completion requires completed tasks plus a merged MR.
- Epic completion rolls up automatically from all persisted child features.
- An accepted, persisted follow-up keeps the epic active; an unaccepted suggestion does not.
- War Room provides an Open MRs view backed by the existing durable review registry.
- Lifecycle reconciliation is idempotent after restart.
- Focused integration tests and one browser-level dashboard flow demonstrate the critical behavior.

## Macro-architecture

Lifecycle decisions remain in the existing authoritative services and durable registries:

1. The central dispatch path evaluates durable feature approval, completed dependencies, and the existing one-feature-awaiting-merge constraint before implementation starts.
2. A lifecycle reconciler derives feature completion from task completion plus MR merge state, then derives epic completion from child-feature state. Reconciliation is idempotent and safe to rerun after restart.
3. A read-only reviews API queries the existing durable review registry. War Room renders an Open MRs view from that API and links directly to each MR.

No parallel approval, lifecycle, or review store is introduced.

## Cross-module constraints

- Approval is durable state separate from board lifecycle status.
- All implementation entry points must pass through the same dispatch eligibility check.
- Dependency readiness means every feature named in `depends_on` is completed.
- Epic approval applies to children present at approval time; features added later require explicit approval.
- Feature completion cannot precede MR merge, even when all tasks are complete.
- Epic completion is derived, never manually asserted by this flow.
- Only a follow-up persisted as an actual child feature participates in completion rollup.
- Review UI and API read from the existing review registry and do not duplicate review state.
- Preserve the current single-feature-awaiting-merge gate.
- Prefer focused integration coverage for lifecycle behavior and one Playwright/browser flow for the dashboard; avoid redundant mock-heavy unit suites.

## Core dependencies

- Existing feature/epic approval persistence and commands, extended only as needed.
- Central feature dispatch/orchestration path and `depends_on` graph.
- Task completion state and durable merge-request/review registry.
- Lifecycle reconciliation/restart recovery mechanism.
- War Room API and frontend routing.

## Feature breakdown

1. **feat_001 — Approval and dependency dispatch**
   - Persist per-feature approval and support epic-wide approval of current children.
   - Centralize dispatch checks for approval, completed dependencies, and the existing merge gate.
   - Establish idempotent recovery behavior for dispatch.
2. **feat_002 — Completion rollup and recovery** (depends on feat_001)
   - Complete features after tasks finish and their MR merges.
   - Roll completion up to the epic across all persisted children.
   - Treat accepted, minted follow-ups as ordinary children and reconcile idempotently.
3. **feat_003 — Open merge requests dashboard** (depends on feat_001 and feat_002)
   - Add a read-only open-reviews API over the existing durable registry.
   - Add the War Room Open MRs view with direct review links.
   - Demonstrate the end-to-end state change with one browser-level flow.

## Open questions

None blocking. Detailed storage/API shapes belong in feature planning and should reuse existing lifecycle and review abstractions.

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-21 · Epic Team · **Lifecycle approval and dispatch**
  Chose Keep approval as durable state separate from board lifecycle status, and enforce approval plus dependency readiness in the central dispatch path..
  Rationale: Approval and status answer different questions; a single dispatch guard prevents alternate entry points from bypassing prerequisites.
  Honors: Per-feature approval, epic-wide approval of current children, dependency-safe implementation dispatch, and restart recovery..

- `dec_002` · 2026-10-21 · Epic Team · **Completion rollup**
  Chose Derive feature completion from completed tasks plus a merged MR, and derive epic completion from all persisted child-feature states..
  Rationale: Derived state avoids premature or manually divergent completion and can be reconciled idempotently after restart.
  Honors: Automatic feature and epic transitions based on content completion..

- `dec_003` · 2026-10-21 · Epic Team · **Follow-up semantics**
  Chose Treat a follow-up as completion-blocking only after it is accepted and minted as an actual child feature..
  Rationale: Free-form suggestions are ambiguous; persisted children provide an auditable boundary without inventing a second backlog state.
  Honors: Keeping an epic active for accepted follow-up work while allowing completion when suggestions are not adopted..
## Amendment log

_(none)_
