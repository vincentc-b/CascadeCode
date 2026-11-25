---
id: epic_053
title: Let parent teams retire superseded child work and reconcile cancellation
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
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Let parent teams retire superseded child work and reconcile cancellation

## Intent

A parent team should be able to retire work that its approved scope has superseded, while keeping historical evidence and maintaining a coherent canonical board. Epic 048 exposed two gaps: feat_048_005 was minted to fix PR #251; the operator subsequently directed the existing Feature 001 team/branch to own that correction, and PR #251 was fixed and merged. Epic decisions dec_008/dec_009 explicitly superseded F5, yet its approved backlog record remained dispatchable in principle. The Epic team had no scoped child-cancellation tool. At 05:06 UTC on 2026-11-25 an operator intervention used the existing cascade cancel CLI to cancel F5, then recorded continue_reduced_scope. The first cancellation-feedback write updated the retained backlog copy of epic_048 on main rather than the authoritative active Epic worktree. A second explicit owner-root call was required to reconcile feedback and the disposition on the active Epic. Prevent this manual intervention and the risk of duplicate implementation or inconsistent parent dispatch/closeout gates.

### Success criteria

1. Introduce supported scoped parent-team tools for proposing/inspecting and applying cancellation of a directly owned superseded child: Epic → Feature and Feature → Task. Start with backlog/unstarted children whose scope is demonstrably superseded by an accepted parent decision or explicit operator instruction. Bind the request to exact parent, child, canonical plan revision, reason, authority and relevant replacement/accepted-delivery evidence. Sibling/foreign work, arbitrary IDs, completed work, and stale decisions must be refused. Do not grant agents unrestricted CLI, Git, process-kill or lifecycle-write authority. If active work or uncommitted changes require additional authorization, retain the evidence and return a typed prerequisite rather than discarding changes or force-cancelling.
2. Reuse the existing cancel_work_item lifecycle, checkpointed teardown and cancellation feedback/disposition mechanisms; do not introduce a competing cancellation ledger or manually move board documents. Separate request, admission, cancellation in progress, cleanup, cancelled and parent disposition. Preserve original approval, plan, decisions, dependencies, historical evidence and parent linkage. One stable request must be replayable across restart without duplicate feedback, teardown, replacement work or paid turns.
3. Resolve the authoritative child and parent documents through the canonical merged-board/owner-worktree routing at each write and recheck under the normal lifecycle/ownership lock. A retained trunk/backlog copy must never receive or override an active parent's cancellation feedback/disposition. Handle colocated and split target/tracking roots, moved/retired worktrees, stale duplicate records, races with parent dispatch/closeout, and partial failure. Do not silently report success when the canonical parent lacks the expected feedback. Provide a supported reconciliation path for existing misrouted records (preserve provenance and decisions; no deletion of history).
4. Keep the current human disposition policy: cancellation alone does not authorize dropping requirements. Support the existing continue_reduced_scope, replace_replan and cancel_parent choices through their legitimate authority, and verify the exact canonical feedback is resolved before releasing gates. Existing explicit human direction or accepted scope decision may be used only where policy already grants that authority; otherwise request a human choice. Cancellation of a superseded child must not be treated as successful implementation or satisfy unrelated acceptance. Do not mint replacement work for an explicitly superseded requirement.
5. Expose cancellation reason, owner, request/cleanup/disposition state and actionable blocker in the existing War Room and team tool results. Parent team must receive durable acknowledgement and verified outcome; no vague completion based on a queued message. Ensure automatic dispatch cannot race an admitted supersession and that rollup handles cancelled children correctly without falsely marking incomplete acceptance complete. Reuse current readable history, avoid mutations or model wakeups from UI GET/poll requests.
6. Acceptance: reproduce Epic 048 with a retained backlog parent copy, canonical active Epic, and an approved superseded backlog Feature. Through the actual parent-team scoped tool, admit authorized cancellation, verify no Feature dispatch/duplicate work, retain history and cleanup, persist feedback and authorized continuation only in the canonical active parent, and prove correct rollup/dispatch after restart. Exercise the analogous Feature → Task route, wrong parent/sibling/terminal/stale request refusal, repeated delivery, supervisor restart between cancellation and feedback, concurrent dispatch/closeout, live or dirty child preservation, missing/unavailable capability and split roots. Include actual operator CLI regression so it follows the same canonical feedback path. Use real temporary repositories/worktrees and supported tools; assert durable state and absence of unintended changes independently, not just success returns.

7. Explicit Epic closeout regression from 2026-11-25: after all implementation Features merged, `epic_048` returned `child_features_incomplete` for cancelled `feat_048_005` despite its canonical active parent recording `continue_reduced_scope`. Preserve the immediate hotfix to `cascade/boss/epic_complete.py`: recognize only terminal, cleanup-complete cancellations with exact matching resolved reduced-scope feedback; keep the cancelled child and its approval/history, and keep absent, unresolved, stale/mismatched, replacement/replan and cancel-parent cases blocked. Verify both the merged-board predicate and the child copies that the Epic implementation review will publish. Extend the same lifecycle correctness to Feature rollup for cancelled Tasks as appropriate, and ensure accepted replacement scope is established before treating a replacement/replan disposition as resolved delivery. Add hosted regression coverage for cancellation, closeout and restart; do not bypass any remaining review, comment, architecture, or validation gate.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Extend the existing cascade/cancellation.py, cancellation_feedback.py, board/workspace canonical document resolution, Epic/Feature scoped registries/guards, Watchdog lifecycle/recovery and rollup. Preserve review/approval authority and existing finite recovery budgets. Coordinate with Epic 051 review-pending team ownership, Epic 048 recovery and Epic 049 progress visibility; this brief is child cancellation and canonical parent reconciliation, not a new review monitor, scheduler or ledger. Implement minimal scoped authority with separate human disposition where needed. Synchronize affected DESIGN.md and architecture views with actual implementation. No live deployment or destructive cleanup authority is granted by filing; keep the brief in backlog for normal approval.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-25 · Human · Brief approved through merge request review.

## Amendment log

- 2026-11-25 · Human-requested amendment: capture the Epic 048 closeout refusal and retain the verified immediate closeout correction; remaining parent-team cancellation and canonical feedback work remains in scope.
