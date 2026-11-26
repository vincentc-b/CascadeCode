---
id: feat_034_009
title: Reconcile completed review recovery admissions in health audits
tier: feature
status: completed
parent: epic_034
children:
- task_034_009_001
depends_on:
- feat_034_006
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 59cba5bd0660b29f8444c0a9837905041ae9c82f
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
  swe: medium
approved_at: '2026-11-10T16:56:46.484857+00:00'
---
# Reconcile completed review recovery admissions in health audits

## Parent Epic

epic_034

## Scope

Repair the proven audit projection defect from investigation_90d4c50f3e8326ebc96bc0186bbb96a5. Preserve completed Feature F and its merged PR #218. This is a bounded audit-projection repair, separate from Feature H's historical evidence and architecture acceptance work. Requires independent review and fresh human approval under epic criteria 17–18 before implementation; the old epic approval does not authorize this corrective feature.

Observed evidence: resolution:v1:e58059ef6a24760191f4653a01e6bf7ebd50260509f8edc865db5067158754ac remains status=mutation_ready in resolution_actions.json, while the same action in executions.json has recovery_state=completed and completion_reconciliation.reason=review_health_restored at 2026-11-10T02:17:15Z. reviews.json marks Feature F closed. GitHub PR #218 is MERGED at d2ed1aca886e61d087fa29842ebca617c0956d96 (2026-11-10T03:35:20Z); Feature F's 47342fb3 is reachable from the owned epic. Main's cascade/watchdog/audit.py _collect_resolution_review_references attributes the nonterminal admission to Feature F without joining authoritative action completion. _reconcile_completed_review in cascade/review_health.py completes the execution recovery but leaves the admission record unchanged.

Architecture impact: no diagram change. The repair stays within existing audit and review-health components and their persisted identities; it introduces no service, store, or cross-owner access.

Acceptance:

1. Reproduce the closed/merged review plus mutation_ready admission plus completed matching recovery case using actual persisted-store shapes. Confirm no unresolved recovery incident remains solely because the historical admission is retained.
2. Use exact action identity and authoritative completion evidence. A closed review alone, unrelated completed action, mismatched identity, unreadable store, or still-live/failed recovery must not suppress a real incident. Preserve audit history and fail visibly on ambiguous evidence.
3. Implement the smallest canonical reconciliation or read-only projection correction; no raw production state edits, review reopening, retry of completed children, or deletion of historical receipts. Keep repeated audit passes idempotent.
4. Add focused integration coverage for the stale admission and live/failed/mismatched/unavailable countercases. Retain existing review identity and nested-handoff regression coverage from main c0c1a891; do not regress or duplicate that already-landed repair.
5. SWE implementation occurs in its isolated task worktree and publishes a canonical review with exact test results. After accepted integration, request fresh authoritative reassessment of the assigned audit case. Repair enqueue or a successful planning turn is not proof of recovery.

### Additional terminal-parent audit correction

The 2026-11-10 A–E investigations (investigation_96ec034b51e42057d6b6b0e84cc87d8e, investigation_a217981361b70bd98a601b6e4ab27061, investigation_665e4c76e4fb559d37c2fe1ee780d142, investigation_835516b46bbe0b8eca73b4fedfa729c1, investigation_6269022dacd38e64a942fa2563e4c9d8) share a second proven projection defect. Canonical supervision reports all five features completed without incidents; their 30 child executions are terminal/succeeded with no last_error or validation failures, and their review registry entries are closed. Deployed audit.py _parent_action_evidence permits the stale-parent candidate for completed features after their worktree is removed; _classification then prioritizes that executable candidate over terminal health. A read-only synthetic probe of the deployed module reproduced resume_owner_with_fresh_parent for completed and cancelled features after two unchanged observations, as well as the valid active-feature control. The probe did not mutate persisted state.

6. Prevent parent-revision drift alone from resuming completed or cancelled features. Preserve their historical parent_rev, accepted commits, approvals and lifecycle state. Do not refresh completed documents merely to silence the audit.
7. Preserve legitimate active-feature stale-parent recovery and genuine terminal cleanup/publication, branch-discrepancy, unresolved-recovery and unavailable-evidence handling. Do not broadly classify every terminal feature as healthy.
8. Add a focused lifecycle regression that completes a feature, removes its integration worktree, then changes the epic revision and observes it across the audit interval: no planning-resume incident should appear. Cover active stale-parent recovery, cancelled-work cleanup and retained unpublished integration work so the fix remains narrow.
9. Bind audit reassessment to each of the five case IDs above after accepted repair. The original F admission correction remains required and independently validated. Historical product acceptance gaps remain Feature H's scope.

This addition supersedes only the earlier review's scope for I: refreshed Architect review and human approval of this revised feature are required before execution. No implementation or successful correction is claimed.

## Data structures

Reuse resolution_actions.json admission identity, executions.json action recovery and completion_reconciliation, and reviews.json owner/review identities. Also reuse canonical lifecycle status, recorded parent_rev and parent observation episodes for terminal-parent eligibility. No new store or broad schema migration. Bind authoritative completion to the exact admission action_id and owning review/work identity; retain historical evidence.

## API contracts

Reuse the existing audit observation and review-health reconciliation paths. Select either canonical admission reconciliation or a read-only join after checking current main implementation. Limit stale-parent resume eligibility to appropriate nonterminal lifecycle states without bypassing other audit evidence. Do not hide all references for completed features or closed reviews. Store-read failures remain unavailable evidence, not healthy status.

## Logic flow

Read scoped admission and recovery evidence; bind exact action identity; validate terminal reconciliation and owner identity; project the resolved historical action without reviving it; preserve genuine pending references; request independent reassessment after accepted repair.

## Task breakdown
- task_034_009_001

One focused SWE audit-projection repair and regression-validation slice covering both the exact admission/completion join and terminal-parent eligibility, followed by normal independent review. Do not dispatch before the new feature's review and human approval.

## Risks & upward questions

The audit source in the epic checkout predates main c0c1a891. Use the current deployed audit behavior for reproduction and retain its identity fixes. Feature H remains separately responsible for unresolved historical and architecture acceptance evidence; this repair cannot declare the epic accepted.

## Decision log

None yet.

## Closeout

Completed child work: `task_034_009_001` (Repair review-recovery and terminal-parent audit projections).
