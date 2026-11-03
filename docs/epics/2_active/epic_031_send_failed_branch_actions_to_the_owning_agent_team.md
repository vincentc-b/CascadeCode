---
id: epic_031
title: Send failed branch actions to the owning agent team
tier: epic
status: active
parent: null
children:
- feat_031_001
- feat_031_002
- feat_031_003
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

Build on the action-recovery records introduced for `epic_026`, existing branch synchronization and merge result types, work queues, and review reconciliation. Extend those paths rather than adding a parallel notification system. The supervisor retains Git and lifecycle mutation authority; agent teams receive scoped evidence and recovery tools. Preserve operator and agent changes, review requirements, source/target provenance, and idempotent completion events. A warning reports an observed failure; it must not claim that agents are investigating until the owning-team request has been durably queued.\n\nOut of scope: autonomous semantic conflict resolution, bypassing review or authorization gates, generalized forge incident management, redesigning all War Room notifications, and failures unrelated to branch/lifecycle actions.

## Macro-architecture

A single recovery coordinator at existing branch and lifecycle command boundaries upserts the `epic_026` durable record from the original action identity and normalized failure, assigns ownership from work tier and intended target, and enqueues one investigation with an episode idempotency key. Existing success behavior remains unchanged.

Only the supervisor mutates Git. Under the lifecycle lock it may validate checkout state, confirm abort/clean state, refresh heads, synchronize safely, and retry within a bound. Teams inspect evidence and choose a scoped resolution or resume the same action; every transition updates the same record projected to API and War Room.

Review reconciliation compares accepted changes with the intended Epic branch, not only forge PR state. A stacked PR that missed the Epic becomes integration-pending; a reviewed follow-up reaches the Epic before idempotent completion releases dependents.

## Cross-module constraints

- Recovery identity is stable across retries, polls, restarts, and resumption; one episode yields at most one warning and queue item.
- Persist safe operator summaries separately from sensitive diagnostics.
- Feature-local work routes to the Feature Team; Epic targets and cross-feature work route to the Epic Team; unknown ownership blocks durably.
- Git mutation stays under the lifecycle lock and revalidates heads, cleanliness, authorization, and review gates.
- Never discard unrelated files, force-push, synthesize approval, or complete before intended-branch integration.
- API/UI consume persisted state; completion, dependent release, delivery, and warning resolution are idempotent.
- Schema changes remain compatible with existing `epic_026` records and in-flight restart.

## Core dependencies

- Existing `epic_026` recovery persistence and transitions.
- Branch synchronization and typed merge/update results.
- Supervisor lifecycle lock, checkout management, and bounded retry.
- Durable Feature Team and Epic Team queues.
- Review reconciliation, completion events, and dependency eligibility.
- War Room API, row projection, and toast behavior.
- Forge source, actual target, intended target, and accepted-revision metadata.

## Feature breakdown

### `feat_031_001` — Durable branch-action recovery and owning-team handoff

Extend the shared record and command boundaries across updates and lifecycle merges. Normalize first failures, route one investigation, provide bounded supervisor repair, and let teams resume the same action. Exit: representative merge, update, checkout, conflict, and permission failures persist and route once; recovery succeeds or names a human blocker.

### `feat_031_002` — War Room recovery status and operator guidance

Project the shared record through the board API and row with truthful copy, owner, safe reason, branch/paths, attempt time, link, and next step. Depends on `feat_031_001`. Exit: API/browser tests preserve exact state across refresh/restart without duplicate notices or premature investigation claims.

### `feat_031_003` — Reconcile stacked reviews into the intended Epic branch

Detect accepted stacked changes absent from the Epic, create the same episode, route to the Epic Team, and drive reviewed follow-up integration while retaining review identity. Depends on `feat_031_001`; may parallel `feat_031_002`. Exit: the `feat_029_002` race stays pending, integrates through review, completes once, and releases its dependent once.

## Open questions

None blocking. Feature planning must confirm the existing `epic_026` schema and queue idempotency fields before migration design, without replacing the shared record or relaxing this contract.

## Decision log

- Use one durable recovery episode for failure, handoff, retry, and UI status.
- Route by intended integration ownership; ambiguous cases block explicitly.
- Forge merge state is evidence only; completion requires presence on the intended Epic branch.
- Automated repair is limited to deterministic, reversible mechanics under the lifecycle lock.
- Ship the recovery core first, then UI and stacked-review work against its contract.

- `dec_001` · 2026-11-03 · Epic Manager · **Recovery model**
  Chose Use one durable recovery episode for command failure, owning-team handoff, supervisor retry, and War Room status..
  Rationale: A shared record preserves action identity and idempotency across all consumers while extending epic_026 instead of adding a parallel incident system.
  Honors: Required behaviors 1–5; implementation boundary to extend existing recovery paths..

- `dec_002` · 2026-11-03 · Epic Manager · **Ownership routing**
  Chose Route by intended integration ownership: Feature Team for Task/Feature-local work, Epic Team for Epic targets and cross-feature integration; persist ambiguous routing as blocked..
  Rationale: The intended target identifies who can resolve the failure, and an explicit blocker prevents silent loss when metadata is incomplete.
  Honors: Required behavior 3 and the operator-visible blocker acceptance scenario..

- `dec_003` · 2026-11-03 · Epic Manager · **Completion semantics**
  Chose Treat forge merge state as evidence only; complete a Feature only after its accepted revision reaches the intended Epic branch..
  Rationale: This directly closes the stacked-review race without bypassing the normal reviewed integration path or losing provenance.
  Honors: Required behavior 6 and the feat_029_002 acceptance scenario..

- `dec_004` · 2026-11-03 · Epic Manager · **Automated repair boundary**
  Chose Limit supervisor repair to bounded, deterministic, reversible mechanics under the lifecycle lock..
  Rationale: Mechanical recovery can be automated safely, while semantic conflicts, dirty unrelated files, authorization, and review gates need an owning-team or human decision.
  Honors: Required behavior 4 and the safety acceptance scenarios..
## Amendment log

_(No amendments.)_
