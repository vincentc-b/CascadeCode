---
id: epic_045
title: Highlight newly added features requiring operator attention
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
created: '2026-11-10'
updated: '2026-11-10'
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
# Highlight newly added features requiring operator attention

## Intent

Make newly added features visibly discoverable in the War Room with a clear New tag, especially when an active Epic team adds corrective work that requires human review and approval.

Observed problem: Epic 034's Feature 007 completed its task execution but left acceptance gaps. The team created feat_034_008 and feat_034_009 as corrective features. The periodic auditor correctly reported waiting for fresh human approval, but the new backlog features were not conspicuous enough. The operator interpreted the lack of progress as a stuck feature or failed auditor. New work awaiting attention must be obvious without reading audit reports or scanning every child row.

Keep the existing workflow and approval boundaries. This is an attention and discovery improvement, not permission to approve or activate corrective work automatically. Prefer a small, consistent New tag and an obvious path to the new feature's plan over another notification stream.

### Success criteria

1. Show an accessible New tag beside newly created features in the normal Epic/Feature board views, including corrective features added after an epic has begun or siblings have completed. Keep lifecycle status visible separately: New describes unseen additions, not a new backlog/active/blocked state.
2. When children are hidden in a collapsed epic, show an aggregate indicator such as 2 new features on the epic row. Provide a direct, discoverable way to reveal those features and open their plans. An off-screen or collapsed addition must not require inspecting audit logs to discover it.
3. Show the relevant existing next action alongside new work when available, such as Awaiting approval, without claiming every new feature requires the same action. Reuse canonical approval/readiness evidence. In the Epic 034 example, 008/009 should be clearly presented as newly added corrective work awaiting review/approval; 007's completed task status must not obscure them.
4. Define and document a deterministic new/unseen lifecycle using stable feature identity and durable creation/acknowledgement evidence. Do not infer newness from filenames, row order, relocation, updated timestamps, branch rebases or status changes. Repeated polling and replay must not recreate the badge after acknowledgement.
5. Provide an explicit, lightweight Mark seen acknowledgement, available from the feature or its review surface. Rendering the board, expanding an epic, scrolling past an item, or an agent reading it must not silently acknowledge it. Acknowledgement only clears the attention marker; it must never approve a plan, activate work, clear a blocker, or satisfy a revision-bound approval gate. Approval can also acknowledge the reviewed feature if consistent with existing UI semantics.
6. Persist acknowledgement across browser refreshes and supervisor restarts using the existing operator/viewer identity model where available. Document whether acknowledgement is per operator or shared by the workspace; do not silently rely only on transient browser memory or introduce an unrelated account system. Respect split tracking/product repository ownership and the existing authorization boundary for writes.
7. Handle the initial rollout explicitly: avoid tagging every historical completed feature as new. Define a conservative bootstrap for already-existing unacknowledged backlog additions under active epics, including the motivating 034_008/009 case if still pending at rollout. Do not reset accepted approvals or create notification floods. Retired/cancelled work must not keep a misleading pending-attention aggregate; retain historical provenance as appropriate.
8. Distinguish first discovery from later plan revisions. Editing an acknowledged feature must not masquerade as creating a new feature or erase the existing changed-plan/approval-required indicators. This brief does not require building a general unread-comments or notification system.
9. Reuse the War Room theme and maintain readable contrast, visible text rather than color alone, keyboard access and useful screen-reader labels. Avoid distracting animation and repeated toast messages on every poll. Keep count and badge updates stable under asynchronous refreshes.
10. Add targeted API/state/UI regressions for newly minted corrective work, collapsed-epic counts, explicit acknowledgement, repeat polling, replay, restart, completed/cancelled children, revised plans and initial bootstrap. Verify that acknowledging newness cannot alter approval/activation state. Include split-root coverage where new state crosses that boundary.
11. Demonstrate the motivating workflow end to end: an active epic adds two corrective features; the operator can immediately see and open them, understand which require approval, mark them seen, and return after refresh without badges reappearing. The original completed sibling remains unchanged and approvals remain explicit.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use Codex as this brief's default provider and preserve explicit role defaults for descendants. Do not change the workspace-wide provider configuration. File this as a backlog brief for normal review and activation; do not implement it while filing.

Keep the change focused on discovering newly added features and their existing next actions. Do not redesign the audit dashboard, implement automatic approval, change task scheduling, or merge unfinished feature work. Coordinate with epic_044's separation of current problems, coverage and history without making this small feature depend unnecessarily on that larger redesign.

Likely areas: War Room board serialization, static/war_room.js and associated templates/styles, existing feature creation metadata and operator-state persistence. Inspect existing identity and acknowledgement conventions before choosing storage. Document creation identity, acknowledgement ownership, bootstrap behavior, approval separation and validation in the design and commit messages.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-10 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
