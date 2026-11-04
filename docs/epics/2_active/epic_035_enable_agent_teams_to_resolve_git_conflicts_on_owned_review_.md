---
id: epic_035
title: Enable agent teams to resolve Git conflicts on owned review branches
tier: epic
status: active
parent: null
children:
- feat_035_001
- feat_035_002
- feat_035_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Enable agent teams to resolve Git conflicts on owned review branches

## Intent

Feature and Epic Teams need their owned open MRs kept mergeable without relying on operators to notice drift. Relevant lifecycle state changes—including feature closure and target-branch movement—must enqueue a lightweight MR-health pipeline that verifies current mergeability. A human “nudge on MR health” is an edge-case trigger into the same pipeline. Healthy reviews complete without an agent turn; a failed check creates one durable recovery action and routes the owning team into a scoped repository-backed turn to inspect real Git history, rebase its open MR branch, resolve code conflicts, test, and push the same branch. On 2026-11-04 the epic_031 team could see only plan.md in a read-only scratch turn when asked to unblock PRs #147 and #148; the Feature Team had the same limitation, so the operator performed both rebases outside Cascade.

### Success criteria

- Relevant lifecycle state changes proactively enqueue deduplicated health checks for affected open MRs; a manual health nudge uses the same path. The tool pipeline records healthy/stale/blocked outcomes and invokes an agent team only when it cannot restore or determine mergeability.
- An assigned Feature or Epic Team can inspect the actual source and target refs, affected paths, review identity, and owned worktree without an operator shell.
- A scoped resolution turn can fetch, rebase, edit semantic conflicts, run relevant tests, and update the existing open MR branch with a remote-head lease. PR #147 resolves its `action_recovery.py` conflict; PR #148 completes its clean rebase.
- The Feature Team can update its own MR branch; the Epic Team can handle Epic-owned and explicitly assigned child Feature branches. A cross-feature decision is handed to one accountable owner.
- Changed remote heads, dirty unrelated files, failed tests, missing Git permissions or credentials, and ambiguous semantic choices stop with durable, actionable War Room blockers. Duplicate requests and restarts do not duplicate commits, pushes, reviews, or completion events.

## Macro-architecture

MR health begins as a cheap, durable, deduplicated pipeline action tied to one open review, its source owner, source ref, target ref, and the observed source and target SHAs. Relevant lifecycle state changes fan out checks only to affected open reviews; an explicit operator nudge enters the same queue. The pipeline resolves review metadata and determines mergeability without launching an agent. A healthy result is persisted and ends the action. A stale, conflicting, indeterminate, or tool-failed result creates or reuses one uniquely identified recovery action and only then invokes the accountable team.

The health pipeline and supervisor resolve the review and ownership records before granting capability. It routes Feature-owned reviews to that Feature Team and Epic-owned or explicitly assigned child reviews to the Epic Team. Cross-feature semantic decisions are not fanned out: one accountable owner is selected and the other teams remain observers.

Execution occurs in a dedicated repository-backed turn for the authorized review worktree, separate from ordinary read-only planning turns. The turn receives only the source/target refs, linked Git metadata, review context, and the minimum fetch/edit/test/push operations needed for that review. Admission rejects closed reviews, unauthorized refs, target branches as push destinations, unrelated or dirty paths, and absent credentials.

The workflow is checkpointed:

1. Inspect and record review identity, ownership, source/target refs, worktree status, and remote source/target SHAs.
2. Fetch and revalidate the recorded heads and authorization immediately before mutation.
3. Rebase the owned source onto the target; if conflicts occur, edit only conflicted/owned paths, then continue the rebase.
4. Run the repository-defined relevant checks and capture their result.
5. Re-read the remote source head and push the rebased source with an explicit `--force-with-lease=<ref>:<observed-sha>`.
6. Persist the resulting head and emit at most one completion event for the action identity.

Every checkpoint is restart-safe. A retry first reconciles local Git state, remote head, and durable action state; it resumes a safe incomplete step or reports a blocker rather than repeating commits, pushes, reviews, or completion messages. Blockers retain the failed checkpoint, observed SHAs, affected paths, command/test summary, and the operator action needed to resume.

## Cross-module constraints

- Extend epic_031 with lifecycle-triggered MR-health checks, deduplication keyed by review and observed heads, recorded health outcomes, and escalation into its existing recovery identity, routing, and War Room state. Accept operator nudges through the same health-check contract.
- Keep ordinary planning scratch turns read-only. Repository and credential access exists only in the admitted resolution turn and only for the authorized review/worktree.
- Permit `--force-with-lease` only for the owned source of an open review, after verifying its recorded remote SHA. Never rewrite target Epic or trunk branches, bypass review/lifecycle gates, discard user files, or expose unrelated checkouts. This narrowly revises epic_031's blanket no-force-push rule.
- Preserve the same PR and accepted-review provenance; recheck branch heads and authorization before each mutation.
- Use structured Git operations or fixed argument vectors for mutations; do not grant an unrestricted operator shell.
- A semantic conflict that cannot be resolved from the owning plan and code is a blocker, not permission to invent product behavior.
- Support every provider that can run Feature or Epic Teams. Provider adapters may launch the turn differently, but share the same admission, capability, state, and result contract.
- Tests must target the high-risk boundaries: authorization/ref confinement, lease rejection, restart reconciliation, and one end-to-end conflict-resolution path. Avoid duplicative mock-heavy coverage already exercised through those workflows.

## Core dependencies

- epic_031's durable recovery-action identity, routing, War Room blocker, retry, and completion-event contracts.
- Lifecycle events and review metadata that identify affected open reviews and authoritatively map each to source ref, target ref, owning Epic/Feature, remote, and observed source/target SHAs.
- A tool pipeline that can query or compute mergeability and persist a health outcome without consuming an agent turn.
- Supervisor support for a repository-backed team turn with narrowly scoped worktree, Git metadata, edit, test, credential, and push capabilities.
- Provider adapters for all supported team runtimes to launch the same resolution-turn contract.
- Existing lifecycle/review gates and repository-defined test commands; this epic extends them but does not replace them.
- Test fixtures capable of modeling linked worktrees, conflicting histories, remote-head races, and interrupted/restarted actions.

## Feature breakdown
- feat_035_003
- feat_035_002
- feat_035_001

1. **Monitor MR health and admit recovery** — trigger deduplicated health checks for affected open MRs on relevant lifecycle state changes; accept a manual nudge through the same path; record healthy outcomes without an agent turn; and convert stale, conflicting, indeterminate, or tool-failed checks into one owned epic_031 recovery action with actionable War Room state.
2. **Execute and publish an owned review rebase** — provide the scoped repository-backed turn; fetch, rebase, edit owned conflicts, run relevant checks, revalidate authorization and heads, and update the same review source ref with an explicit remote-head lease.
3. **Make resolution restart-safe across providers** — reconcile interrupted local/remote/action state, deduplicate side effects and completion events, normalize blocker/resume behavior, and validate provider parity plus the PR #147 conflict and PR #148 clean-rebase acceptance paths.

Features are sequenced 1 → 2 → 3. Feature 2 depends on the health-check and recovery-admission contract; Feature 3 hardens that end-to-end path without broadening its permissions.

## Open questions

None. Implementation-level choices may remain within feature plans, but the safety boundary, ownership model, sequencing, and acceptance paths are fixed here.

## Decision log

- 2026-11-04 · Human · Brief approved through merge request review.
- 2026-11-04 · Epic Manager · Use one durable resolution-action contract for both operator requests and epic_031 recovery routing.
- 2026-11-04 · Epic Manager · Confine mutation to a dedicated repository-backed turn for one authorized open review; ordinary planning remains read-only.
- 2026-11-04 · Epic Manager · Allow history rewrite only through an explicit remote-head lease on the owned review source ref.
- 2026-11-04 · Epic Manager · Deliver in three sequential slices: proactive health monitoring and recovery admission, owned rebase execution, then restart/provider hardening.

- `dec_001` · 2026-11-04 · Epic Manager · **Architecture / request identity**
  Chose Use one durable resolution-action contract for explicit operator requests and epic_031 recovery routing..
  Rationale: A shared identity and state machine prevents duplicated commits, pushes, reviews, and completion events while keeping two request sources behaviorally consistent.
  Honors: Success criteria for explicit requests, recovery actions, durable blockers, and restart idempotency..

- `dec_002` · 2026-11-04 · Epic Manager · **Architecture / capability boundary**
  Chose Confine mutation to a dedicated repository-backed turn for one authorized open review; keep ordinary planning turns read-only..
  Rationale: Teams need real Git history and owned files, but widening every planning turn would expose unrelated checkouts and credentials.
  Honors: The least-privilege and unrelated-checkout constraints in the approved brief..

- `dec_003` · 2026-11-04 · Epic Manager · **Safety / push policy**
  Chose Allow history rewrite only through an explicit remote-head lease on the owned open-review source ref..
  Rationale: Rebase requires rewriting the source branch, while an exact observed-SHA lease and pre-mutation revalidation prevent overwriting concurrent work or target branches.
  Honors: The approved narrow exception to epic_031's no-force-push rule..

- `dec_004` · 2026-11-04 · Epic Manager · **Delivery / feature sequencing**
  Chose Deliver three sequential slices: admission and routing, owned rebase execution, then restart and provider hardening..
  Rationale: This is the smallest sequence that establishes the authorization boundary before mutation and validates reliability without creating a standalone testing project.
  Honors: Ruthless prioritization and the requirement to support all team providers safely..
## Amendment log

_(none)_
