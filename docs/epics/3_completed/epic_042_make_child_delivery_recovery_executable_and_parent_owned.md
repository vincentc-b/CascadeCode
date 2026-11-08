---
id: epic_042
title: Make child delivery recovery executable and parent-owned
tier: epic
status: completed
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-07'
updated: '2026-11-08'
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
# Make child delivery recovery executable and parent-owned

## Intent

Make every Task accountable for its delivery through successful integration into its owning Feature, and give each parent team concrete authority to monitor and safely unblock direct children. A merge or review conflict must route to an actual work ID and wake a team with an executable recovery operation, not persist a generic owner category with no recipient. Task teams should resolve their owned branch, run work-specific supervised validation, and republish the same delivery; Feature teams can inspect, ping, resume, or supervise recovery of their Tasks, and Epic teams have the analogous controls for Features. The War Room must show who owns the delivery, whether the request was delivered and acknowledged, what mutation is authorized, and the eventual result. Under the current stacked architecture, Task-to-Feature delivery is local rather than a forge MR; present it as a first-class owned delivery review and do not label it a forge MR unless a real review exists.

### Success criteria

1. Give every active Task delivery a concrete owner identity, Task branch, Feature target, validation generation, durable action, and visible state through merged or terminally escalated completion.
2. Route a Task-to-Feature semantic conflict first to the Task team that owns the source branch, with the parent Feature team as supervisor. Persist concrete work IDs, enqueue one deduplicated recovery request, wake completed or idle owners when necessary, and record delivery, acknowledgement, decision, mutation, validation, and outcome.
3. Provide a supervised Task recovery operation that attaches to the existing Task branch/worktree, integrates the current Feature head, permits scoped conflict edits, runs Task/plan-defined validation, replaces exact-SHA delivery evidence, and resumes the same durable merge action. It must never reset, clean, force-push, bypass approvals, or silently create another Task.
4. Give Feature teams direct-report controls to inspect health, ping the Task, request safe resume/revalidation/requeue, and take over supervision when the Task owner is absent. Give Epic teams equivalent controls for child Features and their review/publication lifecycle.
5. Make derived parent blockage compatible with child recovery. Resolving a child incident must atomically clear or suspend only that incident's monitoring blocker before retrying its merge; an unrelated blocker remains. A blocked parent must not make the exact child repair impossible.
6. Allow a transient lifecycle refusal after an approved repair, including not_active caused by derived parent blockage, to remain retryable. Do not terminalize the original action unless current authoritative state proves it cannot safely continue; changed facts create a revalidated generation.
7. Replace generic feature_team/epic_team owner decisions with concrete routed ownership everywhere, or fail visibly with an actionable routing blocker. A UI state such as investigating is valid only when a durable request has a recipient and pending/acknowledged status.
8. Use repository- or work-plan-defined supervised validation for conflict publication. Do not hard-code Cascade's own test path or accept an unvalidated conflict resolution.
9. Cover task_037_003_005 end to end: one-file Task conflict, concrete Task and Feature routing, additive conflict resolution, detection of the process_lock-to-recovery_ledger_lock semantic mismatch, eleven green tests, parent blocker reconciliation, rearmed original action, exactly one merge, and terminal success without human JSON edits.
10. Cover a child whose owner process has exited, concurrent parent/periodic recovery, multiple sibling blockers, restart between acknowledgement and validation, and a completed team woken for an owned recovery. Prove no duplicate workers, validations, queue entries, merges, or reviews.
11. Make the Task delivery representation explicit in the War Room. If Task branches remain local, expose an owned delivery-review surface with the same conflict and validation evidence; if per-Task forge reviews are introduced, preserve stacked targets and exact-head leases and make the architectural migration explicit.
12. Preserve durable dispatch authorization across queue consumption, restart, local completion, and review publication. The watchdog must not classify or move a legitimate active parent copy as an illegal dispatch during the completed-in-integration to review-pending handoff. Cover the repeated feat_038_003, feat_039_001, and feat_039_003 event ordering while retaining fail-closed rejection of truly unauthorized moves.
13. Reconcile historical action state with authoritative completion. If a canonical merge or review completes after an earlier action terminalized, record an idempotent completed-equivalent outcome and clear the active incident without erasing failed attempts. A successfully completed Task must not retain an actionable blocked delivery forever.
14. Treat unknown review mergeability, missing owned worktrees, fetch failures, stale-head admission refusals, validation failures, and publication failures as durable owned incidents. Route them to a concrete Feature or Epic team with bounded retry or an actionable blocker; the review poller must not silently skip them or leave a blocked action unreachable.

## Macro-architecture

Implemented through the existing supervised lifecycle, durable recovery actions, owned worktrees, and validation gates. See final delivery below.

## Cross-module constraints

Build on durable action recovery, Task worktrees/checkpoints, execution leases, queued Task merges, Feature/Epic integration worktrees, review recovery, direct-report health, and monitoring-blocker provenance. Keep Git mutation inside the owning worktree or supervised operation and retain explicit dependency-install authorization. Do not grant cross-team arbitrary repository access, weaken exact-SHA validation, allow parents to rewrite unrelated child work, automatically choose ambiguous semantic resolutions, or add a second queue/status system. Preserve action history and accepted commits. Parent authority is scoped to direct descendants and must recheck ownership, leases, current heads, worktree cleanliness, approvals, and dependency readiness under the existing lock order.

## Core dependencies

Uses existing project infrastructure; no new external package or installation.

## Feature breakdown

Delivered directly on main under the operator request. No synthetic child plans or review records are created.

## Open questions

None outstanding for this brief; the earlier audit gaps are resolved by the final delivery below.

## Decision log

- 2026-11-07 · Human · Brief approved through merge request review.

## Amendment log

_(none)_

## Implementation audit · 2026-11-08

Status: open; partial implementation in `b55abca2`. The prior blanket completion claim is withdrawn. No acceptance criteria are waived.

- Task conflict recovery now crosses real resume, scoped validation, parent-blocker reconciliation, and the original merge action; local delivery evidence and concrete routing are implemented.
- Criterion 14 remains incomplete: routed `review_health` incidents do not themselves provide the admitted mutation action required by review-resolution publication. A review becoming healthy while still open also needs reconciliation of the prior health incident.
- Criteria 1 and 11 remain incomplete: completed Task serialization omits delivery action/validation details, so the evidence is not visible through terminal completion.
- Criteria 9 and 10 need the exact semantic-lock-mismatch scenario, multiple sibling blockers, and restart between acknowledgement and validation. Existing narrower successful recovery tests are not substitutes for these cases.

## Final direct delivery · 2026-11-08

Status: completed. Implementation through `a37f05ff` and preceding commits supersedes the earlier partial-completion audit. The operator explicitly requested implementation directly on main because the affected tool could not reliably implement its own repairs. No acceptance criteria are waived.

All acceptance criteria are implemented. Review-health inquiries now re-enter current-head admission through the existing owner-checked publication tool, instead of directing teams to an operation that cannot accept their action. Fetch/snapshot/worktree/admission failures retain concrete owners and actionable retry instructions. Healthy or integrated reviews reconcile obsolete incidents; recurring failures create a new deduplicated generation. Validation/publication failure remains owned, preserves failed attempts, and can retry the same action. Acknowledgements are durably persisted.

Task delivery evidence remains visible after completion. The board preloads action/queue data once per response, retaining terminal validation and attempt history without invoking recovery controls for completed Tasks. Task lifecycle locks and execution/action/orphan/queue storage resolve to one canonical tracking trunk across owned worktrees; source Git operations remain in the product repository. MCP subprocesses preserve repository context across launch.

Acceptance includes the one-file semantic conflict and process_lock/recovery_ledger_lock mismatch: eleven tests fail for the wrong lock, the owning Task fixes it additively, eleven pass, and the original action merges once. Restart after acknowledgement and multiple sibling incidents are covered; the unrelated sibling blocker survives. Existing completed-team wakeup, concurrent recovery, and the three named Feature dispatch-authorization sequences are included. See `tests/test_task_recovery_generations_regressions.py`, `tests/test_review_health.py`, `tests/task/test_lifecycle_lock.py`, `tests/test_war_room_autonomy_regressions.py`, `tests/workspace/test_completed_recovery_kickoff.py`, and `tests/war_room/test_board_recovery_cost.py`.

Validation: the combined affected acceptance suite passed 164 tests; additional targeted crash, failure, and cross-process checks passed. This records scoped acceptance, not a claim that every unrelated repository test passes.
