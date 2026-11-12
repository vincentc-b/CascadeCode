---
id: epic_045
title: Explain feature activation requirements and highlight newly added work
tier: epic
status: active
parent: null
children:
- feat_045_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-10'
updated: '2026-11-12'
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
# Explain feature activation requirements and highlight newly added work

## Intent

Make it clear why each feature has not started, what must happen next, and whether the next action belongs to the operator, another team, or the scheduler. Preserve a clear New tag for newly added features, especially corrective work needing human attention, as part of this broader activation-readiness experience.

A second live example shows why a New tag alone is insufficient. On 2026-11-10 around 17:01 UTC, feat_034_008 was approved, both declared dependencies (006 and 007) were satisfied, and its Codex provider configuration was supported. PR #219 for 007 had merged. Its readiness response nevertheless contained sibling_blocked because feat_034_009 was active and the scheduler serializes active features within an epic. This is an expected scheduling wait, not a missing dependency or missing approval. The UI should identify the actual sibling and explain the scheduling rule, for example: Waiting for feat_034_009 to finish; no action needed from you. This snapshot is a regression scenario, not hard-coded production text.

Observed problem: Epic 034's Feature 007 completed its task execution but left acceptance gaps. The team created feat_034_008 and feat_034_009 as corrective features. The periodic auditor correctly reported waiting for fresh human approval, but the new backlog features were not conspicuous enough. The operator interpreted the lack of progress as a stuck feature or failed auditor. New work awaiting attention must be obvious without reading audit reports or scanning every child row.

Keep the existing workflow and approval boundaries. This is an explanation and discovery improvement, not permission to approve or activate corrective work automatically or to change serial/stacked scheduling policy. Provide a compact reason and next action on the board, with details on demand, alongside the New tag. Do not introduce another noisy notification stream.

### Success criteria

1. Present a concise activation summary for every not-yet-active feature: needs your action, waiting for another work item/system action, ready and awaiting dispatch, or readiness unavailable. Explain what must happen next, who owns it and whether an operator action is necessary. Never describe an expected sibling scheduling wait as failed execution or missing approval.
2. Expand authoritative readiness into structured reasons with stable codes, readable explanations, affected work IDs, relevant review links, observation freshness and available actions. Cover approval or revision reapproval, dependencies, another active sibling, outstanding merge/review, inactive/cancelling parent, dispatch-base availability, blocking review threads and provider configuration/preflight. Reuse the canonical evaluations used at action boundaries; do not duplicate gate logic in JavaScript or launch expensive provider/Git checks from each browser poll.
3. Identify the actual blocking sibling(s) for sibling_blocked and distinguish active execution from pending merge/review. For the 034_008 example, show approved and dependencies satisfied, name/link 034_009, explain the one-active-feature rule, and say the scheduler can proceed when that restriction clears, subject to fresh readiness. Do not invent a declared dependency on the sibling or promise a specific start time.
4. Show a primary reason with expandable additional blockers and satisfied prerequisites so the operator can distinguish missing human action from normal sequencing. Reuse existing dependency displays rather than duplicating them. Link approval, plan review, blocking threads, required merge or provider configuration to the appropriate existing action. Missing or stale evidence must be marked unknown/rechecking rather than converted to ready or a misleading definitive wait.
5. Make ready-but-not-dispatched visible as a distinct state with last evaluation/dispatch-attempt evidence where available. Do not claim a feature is running merely because gates passed. On an actual dispatch refusal, surface the fresh refusal and its actionable explanation; update when dependencies, approvals, sibling execution, reviews or configuration change. Polling and rendering must neither trigger dispatch nor mutate lifecycle state.
6. Show an accessible New tag beside newly created features in the normal Epic/Feature board views, including corrective features added after an epic has begun or siblings have completed. Keep lifecycle status visible separately: New describes unseen additions, not a new backlog/active/blocked state.
7. When children are hidden in a collapsed epic, show an aggregate indicator such as 2 new features on the epic row. Provide a direct, discoverable way to reveal those features and open their plans. An off-screen or collapsed addition must not require inspecting audit logs to discover it.
8. Show the relevant existing next action alongside new work when available, such as Awaiting approval, without claiming every new feature requires the same action. Reuse canonical approval/readiness evidence. In the Epic 034 example, 008/009 should be clearly presented as newly added corrective work awaiting review/approval; 007's completed task status must not obscure them.
9. Define and document a deterministic new/unseen lifecycle using stable feature identity and durable creation/acknowledgement evidence. Do not infer newness from filenames, row order, relocation, updated timestamps, branch rebases or status changes. Repeated polling and replay must not recreate the badge after acknowledgement.
10. Provide an explicit, lightweight Mark seen acknowledgement, available from the feature or its review surface. Rendering the board, expanding an epic, scrolling past an item, or an agent reading it must not silently acknowledge it. Acknowledgement only clears the attention marker; it must never approve a plan, activate work, clear a blocker, or satisfy a revision-bound approval gate. Approval can also acknowledge the reviewed feature if consistent with existing UI semantics.
11. Persist acknowledgement across browser refreshes and supervisor restarts using the existing operator/viewer identity model where available. Document whether acknowledgement is per operator or shared by the workspace; do not silently rely only on transient browser memory or introduce an unrelated account system. Respect split tracking/product repository ownership and the existing authorization boundary for writes.
12. Handle the initial rollout explicitly: avoid tagging every historical completed feature as new. Define a conservative bootstrap for already-existing unacknowledged backlog additions under active epics, including the motivating 034_008/009 case if still pending at rollout. Do not reset accepted approvals or create notification floods. Retired/cancelled work must not keep a misleading pending-attention aggregate; retain historical provenance as appropriate.
13. Distinguish first discovery from later plan revisions. Editing an acknowledged feature must not masquerade as creating a new feature or erase the existing changed-plan/approval-required indicators. This brief does not require building a general unread-comments or notification system.
14. Reuse the War Room theme and maintain readable contrast, visible text rather than color alone, keyboard access and useful screen-reader labels. Avoid distracting animation and repeated toast messages on every poll. Keep count and badge updates stable under asynchronous refreshes.
15. Add targeted API/state/UI regressions for newly minted corrective work, collapsed-epic counts, explicit acknowledgement, repeat polling, replay, restart, completed/cancelled children, revised plans and initial bootstrap. Verify that acknowledging newness cannot alter approval/activation state. Include split-root coverage where new state crosses that boundary.
16. Demonstrate the motivating workflow end to end: an active epic adds two corrective features; the operator can immediately see and open them, understand which require approval, mark them seen, and return after refresh without badges reappearing. The original completed sibling remains unchanged and approvals remain explicit.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use Codex as this brief's default provider and preserve explicit role defaults for descendants. Do not change the workspace-wide provider configuration. File this as a backlog brief for normal review and activation; do not implement it while filing.

Keep the change focused on explaining feature activation requirements and discovering new work. Do not redesign the audit dashboard, implement automatic approval, change serial/stacked dispatch policy or task scheduling, or merge unfinished feature work. Coordinate with epic_044's separation of current problems, coverage and history without making this small feature depend unnecessarily on that larger redesign.

Likely areas: cascade/feature/readiness.py, cascade/stacked_dispatch.py, Boss/dispatch refusal projections, War Room board serialization, static/war_room.js and associated templates/styles, existing feature creation metadata and operator-state persistence. Extend the authoritative readiness projection with blocker identities rather than reverse-engineering them from UI labels. Inspect existing identity and acknowledgement conventions before choosing storage. Document the readiness/explanation contract, source of each blocking fact, creation identity, acknowledgement ownership, bootstrap behavior, approval separation and validation in the design and commit messages.

Additional validation: reproduce 034_008 approved + dependencies satisfied + supported provider + active sibling 034_009, then transition the sibling to completion and confirm the explanation changes according to fresh readiness without an extra approval. Cover multiple simultaneous blockers, pending review versus active execution, an inactive parent, changed-plan approval, unavailable evidence, valid empty blockers awaiting scheduler dispatch, and an actual dispatch refusal. Verify that explaining or acknowledging a reason does not bypass the canonical gate or alter scheduling policy.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_045_001

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-10 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
