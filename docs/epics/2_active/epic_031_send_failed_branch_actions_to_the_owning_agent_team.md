---
id: epic_031
title: Send failed branch actions to the owning agent team
tier: epic
status: active
parent: null
children:
- feat_031_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-02'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Send failed branch actions to the owning agent team

## Intent

When a branch update, merge, or review reconciliation does not succeed on its first attempt, keep the action open and send its failure to the agent team that owns the affected work. Show a durable War Room warning such as **“Merge failed; agents are investigating”** while recovery is in progress. The operator should see the eventual resolution or a specific blocker without having to discover and repair a silent Git or lifecycle failure.

Two incidents show the gap. Updating `epic_029` returned a `branch_conflict` for three `epic_030` documents, but the War Room route only returned a 409 and conflict paths; no recovery action or Epic Team message was created. PR #125 for `feat_029_002` merged into its stacked predecessor, `feat/feat_029_001`, after that predecessor had merged into `epic/epic_029`. The review poller only finalizes an accepted Feature review whose target is an Epic branch. The Feature document is completed in its source worktree, but the board still labels PR #125 “Awaiting review,” no completion event has reached the Epic, and the accepted changes are absent from the Epic branch. The poller silently retries finalization without an owning-team handoff.

## Required behavior

1. Apply one failure-handling boundary to operator-triggered and automatic branch updates, Task-to-Feature merges, Feature-to-Epic merges, Epic promotion/close merges, and merged-review reconciliation. A typed unsuccessful result, thrown error, or accepted review whose changes have not reached the intended integration branch must enter the boundary on the first failed attempt. Preserve the original action ID, authorization, source and target refs, and review identity.
2. Persist the action's failure reason, safe summary, conflicting paths if any, source and target revisions, owning checkout, attempt count, recovery state, and next step. Record whether the merge was aborted or left a clean checkout. Make the record visible after refresh and supervisor restart. Do not equate a forge's “merged” flag with integration into the intended Epic branch.
3. Immediately notify the owning team through its normal durable queue, with the action reference and enough evidence to investigate. The Feature Team owns Task and Feature-local conflicts; the Epic Team owns Epic branch updates, cross-feature integration, and Epic contract decisions. If ownership is ambiguous, surface an explicit routing blocker instead of dropping the failure. Deduplicate notifications so retries and polling do not start duplicate turns.
4. Let the supervisor perform bounded, deterministic repair under the existing lifecycle lock, including checkout repair, clean retry, and safe branch synchronization. The owning team can inspect the failure, make a scoped code or plan resolution, and request resumption of the same action. Give the team a real recovery command or resolution path; recording an owner label alone is insufficient. Recheck branch heads and lifecycle gates before retrying, and stop when the original action succeeds or reaches a human gate.
5. Show a warning on the affected War Room row as soon as the first attempt fails: **“Branch update failed; agents are investigating”**, **“Merge failed; agents are investigating”**, or **“Review merged; integration is still pending”**, as appropriate. Include the owning team, reason, affected paths or branch, last attempt, and a link to the action or review. Update it to resolved, awaiting human review, or blocked with a precise next step. Avoid repeated failure toasts for one incident.
6. Reconcile stacked Feature reviews against the intended Epic integration branch. If a child PR lands on a predecessor after that predecessor's Epic PR merged, do not mark the child complete or release dependents until its accepted changes reach the Epic branch through the normal reviewed path. Escalate a stale or immutable PR base to the Epic Team with an actionable integration plan and preserve the original review provenance.

## Acceptance scenarios

- A first `Update branch` conflict on an Epic aborts cleanly, creates one durable recovery action, warns the Epic row, and queues one Epic Team investigation. Resolving the unrelated-document conflict and retrying the same action clears the warning.
- A Task-to-Feature code conflict reaches the Feature Team; a Feature-to-Epic or Epic promotion conflict reaches the Epic Team. Each team can record a resolution and resume the original action without an operator Git command.
- A missing checkout or transient Git/forge error receives immediate team visibility while the supervisor attempts bounded mechanical repair. Repeated polls, clicks, and restarts do not duplicate turns, merges, reviews, or warnings.
- A review merged into a stacked predecessor after that predecessor merged into the Epic remains visibly pending integration. The accepted changes reach the Epic through a reviewed follow-up, then the Feature completes and its dependent Feature becomes eligible exactly once.
- A permission failure, dirty unrelated checkout, ambiguous semantic conflict, or unmet human review gate retains the warning with a specific owner and next step. Recovery never discards user files or bypasses approval.
- API, supervisor, board, and browser tests verify first-failure delivery, owner routing, durable warning transitions, recovery success, and the stacked-review race represented by `feat_029_002`.

## Implementation boundaries

Build on the action-recovery records introduced for `epic_026`, existing branch synchronization and merge result types, work queues, and review reconciliation. Extend those paths rather than adding a parallel notification system. The supervisor retains Git and lifecycle mutation authority; agent teams receive scoped evidence and recovery tools. Preserve operator and agent changes, review requirements, source/target provenance, and idempotent completion events. A warning reports an observed failure; it must not claim that agents are investigating until the owning-team request has been durably queued.

## Macro-architecture

_(To be developed during Epic planning.)_

## Cross-module constraints

_(To be developed during Epic planning.)_

## Core dependencies

_(To be developed during Epic planning.)_

## Feature breakdown
- feat_031_001

_(To be developed during Epic planning.)_

## Open questions

_(To be developed during Epic planning.)_

## Decision log

_(To be developed during Epic planning.)_

## Amendment log

_(To be developed during Epic planning.)_
