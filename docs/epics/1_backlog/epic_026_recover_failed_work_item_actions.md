---
id: epic_026
title: Recover failed work item actions
tier: epic
status: backlog
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

When a user or team requests an action on an epic, feature, or task, Cascade should try to complete it or repair a recoverable failure without asking the user to run Git commands or clean a checkout. The initiating action remains pending while recovery runs, then finishes or reports a precise blocker. In particular, closing an epic must work when the operator's product trunk checkout has unrelated tracked or untracked changes.

### Success criteria

- A failed action carries a typed reason, affected work item, owning checkout or branch, retry state, and safe next step. The War Room shows that recovery is underway and the eventual result; it does not turn a recoverable first failure into a terminal refusal.
- The supervisor handles deterministic task failures and repository mechanics with scoped operations. It can retry or resume the existing Task run, repair a missing integration checkout, use an isolated checkout for trunk operations, and retry a merge after its preconditions are restored. The Feature Team handles task decisions that require code or plan judgment; the Epic Team handles feature and epic decisions. Parent teams can request recovery, and the supervisor owns scheduling, locks, and execution.
- Epic close succeeds with a dirty operator trunk by using the existing reviewed-branch and isolated closeout-review path. It never commits, stashes, resets, cleans, or merges unrelated operator changes. A merged implementation review and terminal closeout review are verified before completion is recorded.
- Safe recovery preserves action identity and authorization: retries are bounded, durable, idempotent, serialized with lifecycle mutations, and resume after supervisor restart without duplicate turns, PRs, merges, or completion events.
- Missing credentials, unavailable services, insufficient permissions, human review gates, ambiguous semantic conflicts, and unrelated dirty integration files become explicit blockers with ownership and a retry path. Recovery does not silently grant agents broader permissions or bypass a human decision.

## Macro-architecture

Introduce a shared action-recovery boundary around epic, feature, and task actions. Persist the requested action and its recovery state, classify failures from the existing typed lifecycle results, and choose a bounded remedy. Retry the original action only after re-reading current board, branch, review, lease, and permission state under the lifecycle lock. Keep the supervisor as the coordinator and privileged executor for routine Git and Task-run repairs; give parent teams scoped recovery requests and the context needed for decisions beyond deterministic repair.

For trunk operations, use a clean temporary worktree based on the verified remote product trunk and open or reuse the normal review. For integration worktree changes, preserve local files and return work to the owning agent when validation or semantic conflict resolution is needed. Record every attempt and its outcome in the action history. The War Room should expose pending, repairing, awaiting review, blocked, and completed states, with a single retry control for terminal blockers after the underlying condition changes.

## Cross-module constraints

- Preserve all user and agent changes. Never automatically discard, reset, clean, force-push, or stash a checkout. Do not absorb unrelated files into an action commit or PR.
- Respect existing human approval, comment, review, and authorization gates. The original request authorizes retries of that action, but does not authorize merging an unreviewed PR or changing credentials and permissions.
- Let simple supervisors perform deterministic task recovery; do not require a high-cost planning model for routine retry, lease, checkout, or merge-queue repair. Escalate code and product decisions to the owning team with enough context to act.
- Prevent loops with an attempt limit, backoff for transient failures, and a terminal typed blocker. Serialize concurrent user, team, and automatic recovery requests for the same action.
- Reuse `branch_synchronization`, integration worktrees, task execution and merge queues, review tracking, and the existing lifecycle event contracts. Keep branch provenance and the selected review target stable.

## Core dependencies

- Existing supervisor, Task execution lease, checkpoint, and pending merge queue.
- Epic, feature, and task lifecycle actions and their typed failure results.
- Integration worktree and branch synchronization services.
- Review tracking and forge authentication for review creation and verification.
- War Room action routes, status model, and recovery controls.

## Feature breakdown

The Epic Team will sequence focused slices for the recovery state machine, supervisor and parent-team ownership, dirty-trunk epic close, and War Room feedback. Cover a dirty operator trunk, recoverable Task interruption, feature merge conflict, transient forge failure, permission refusal, and concurrent retry in integration tests.

## Open questions

- Which existing supervisor actions can be made deterministic without giving Task workers broader Git or forge permissions?
- Where should a semantic conflict handoff appear so the owning team can resolve it and the original action can resume?

## Decision log

- 2026-10-26 · Human · Brief proposed for review after epic_009 close exposed a dirty product trunk checkout.

## Amendment log

_(none)_
