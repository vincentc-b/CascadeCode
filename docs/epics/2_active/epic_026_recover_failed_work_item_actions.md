---
id: epic_026
title: Recover failed work item actions
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
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Recover failed work item actions

## Intent

When a user or team requests an action on an epic, feature, or task, Cascade should complete it or repair a recoverable failure without asking the user to run Git commands or clean a checkout. The initiating action remains pending while recovery runs, then finishes or reports a precise blocker. In particular, closing an epic must work when the operator's product trunk checkout has unrelated tracked or untracked changes.

### Success criteria

- A failed action carries a typed reason, affected work item, owning checkout or branch, retry state, and safe next step. The War Room shows that recovery is underway and the eventual result; it does not turn a recoverable first failure into a terminal refusal.
- The supervisor handles deterministic task failures and repository mechanics with scoped operations. It can retry or resume the existing Task run, repair a missing integration checkout, use an isolated checkout for trunk operations, and retry a merge after its preconditions are restored.
- The Feature Team handles task decisions requiring code or feature-plan judgment; the Epic Team handles cross-feature and epic-plan decisions. Parent teams can request recovery, while the supervisor owns scheduling, locks, and execution.
- Epic close succeeds with a dirty operator trunk by using the existing reviewed-branch and isolated closeout-review path. It never commits, stashes, resets, cleans, or merges unrelated operator changes. A merged implementation review and terminal closeout review are verified before completion is recorded.
- Safe recovery preserves action identity and authorization: retries are bounded, durable, idempotent, serialized with lifecycle mutations, and resume after supervisor restart without duplicate turns, reviews, merges, or completion events.
- Missing credentials, unavailable services, insufficient permissions, human review gates, ambiguous semantic conflicts, and unrelated dirty integration files become explicit blockers with ownership and a retry path. Recovery does not grant broader permissions or bypass a human decision.

## Macro-architecture

Introduce a shared action-recovery boundary around epic, feature, and task lifecycle actions. Persist the requested action and recovery state, classify failures from existing typed lifecycle results, and choose a bounded remedy. Retry the original action only after re-reading current board, branch, review, lease, and permission state under the lifecycle lock.

The supervisor is the coordinator and privileged executor for deterministic Git and Task-run repairs. Parent teams receive scoped recovery requests only when a remedy requires code or plan judgment. A semantic task conflict is handed to the Feature Team; a cross-feature or epic-contract conflict is handed to the Epic Team. The same persisted action resumes after that team records a resolution.

For trunk operations, use a clean temporary worktree based on the verified remote product trunk and open or reuse the normal review. For integration worktree changes, preserve local files and return work to the owning agent when validation or semantic conflict resolution is needed. Record every attempt and outcome in action history. The War Room exposes pending, repairing, awaiting decision or review, blocked, and completed states, with one retry control for terminal blockers after the underlying condition changes.

## Cross-module constraints

- Preserve all user and agent changes. Never automatically discard, reset, clean, force-push, or stash a checkout. Do not absorb unrelated files into an action commit or review.
- Respect existing human approval, comment, review, and authorization gates. The original request authorizes bounded retries of that action, but not merging an unreviewed change or changing credentials and permissions.
- Keep Task workers' current Git and forge permissions unchanged. Deterministic recovery belongs to the supervisor's existing privileged execution boundary.
- Prevent loops with a configurable attempt limit, backoff for transient failures, and a terminal typed blocker. Serialize user, team, and automatic recovery requests for the same action.
- Reuse branch synchronization, integration worktrees, Task execution and merge queues, review tracking, and existing lifecycle event contracts. Keep branch provenance and the selected review target stable.
- Do not build a generic workflow engine, arbitrary rollback, or automatic semantic conflict resolver in this epic.

## Core dependencies

- Existing supervisor, Task execution lease, checkpoint, and pending merge queue.
- Epic, feature, and task lifecycle actions and their typed failure results.
- Integration worktree and branch synchronization services.
- Review tracking and forge authentication for review creation and verification.
- War Room action routes, status model, and recovery controls.

## Feature breakdown

1. **Durable action recovery state**
   - Add a stable action identity and persisted recovery state around lifecycle actions.
   - Classify existing failures into deterministic repair, transient retry, owner decision, human gate, and terminal blocker.
   - Enforce serialization, bounded attempts, idempotent resumption after restart, and attempt history.
   - Acceptance: restart and concurrent-retry integration tests prove one logical action produces no duplicate team turns, reviews, merges, or completion events.

2. **Supervisor repair and owning-team handoff**
   - Implement only deterministic remedies needed by current lifecycle failures: resume an interrupted Task run, restore a missing integration checkout, and retry a queued merge after mechanical preconditions recover.
   - Route semantic task/code conflicts to the Feature Team and cross-feature or epic-contract conflicts to the Epic Team, including action context and a resume token/reference.
   - Acceptance: interrupted Task and feature merge-conflict scenarios either resume to completion or enter the correct owned decision state without widening worker permissions.

3. **Dirty-trunk-safe epic close**
   - Run trunk-dependent closeout work in an isolated checkout based on verified remote product trunk.
   - Reuse or open the normal closeout review, verify the implementation review is merged and terminal closeout review is satisfied, then resume the original close action.
   - Acceptance: an epic closes while the operator trunk contains unrelated tracked and untracked files; those files and the operator checkout remain byte-for-byte and index-state unchanged.

4. **War Room recovery feedback and retry**
   - Show recovery phase, typed reason, attempt count, owning actor, affected checkout or branch, and next safe step on the original action.
   - Provide a single retry control only for retryable terminal blockers; keep approval and review gates distinct.
   - Acceptance: transient forge failure, permission refusal, and concurrent retry scenarios display the correct state and produce at most one resumed execution.

## Delivery order

Deliver features 1 and 2 first because all recovery paths depend on durable identity and ownership. Feature 3 then applies the boundary to the initiating dirty-trunk defect. Feature 4 exposes the established state model without creating a second orchestration path.

## Open questions

_(none)_

## Decision log

- 2026-10-26 · Human · Brief proposed for review after epic_009 close exposed a dirty product trunk checkout.
- 2026-10-26 · Epic Manager · Keep Task worker permissions unchanged; place deterministic recovery in the supervisor boundary.
- 2026-10-26 · Epic Manager · Route semantic task/code conflicts to the Feature Team and cross-feature or epic-contract conflicts to the Epic Team; resume the original persisted action after resolution.
- 2026-10-26 · Epic Manager · Limit the epic to current lifecycle recovery paths; exclude a generic workflow engine, arbitrary rollback, and automatic semantic conflict resolution.

- `dec_001` · 2026-10-26 · Epic Manager · **Cross-module constraints**
  Chose Keep Task worker permissions unchanged; deterministic recovery runs inside the supervisor's existing privileged execution boundary..
  Rationale: Routine checkout, lease, and merge-queue repair does not require product judgment and must not broaden worker authority.
  Honors: Success criteria requiring scoped supervisor repair without broader permissions..

- `dec_002` · 2026-10-26 · Epic Manager · **Macro-architecture**
  Chose Route semantic task/code conflicts to the Feature Team and cross-feature or epic-contract conflicts to the Epic Team, then resume the same persisted action after resolution..
  Rationale: The owning planning level should decide semantics while the supervisor retains scheduling, locking, and execution.
  Honors: The ownership model and action-identity requirements in the epic intent..

- `dec_003` · 2026-10-26 · Epic Manager · **Cross-module constraints**
  Chose Exclude a generic workflow engine, arbitrary rollback, and automatic semantic conflict resolution..
  Rationale: These additions are not necessary to recover the known lifecycle failures and would materially expand cost and risk.
  Honors: The smallest shippable slice for reliable action recovery..
## Amendment log

_(none)_
