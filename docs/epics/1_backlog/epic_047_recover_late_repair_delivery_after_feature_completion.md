---
id: epic_047
title: Recover late repair delivery after feature completion
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
# Recover late repair delivery after feature completion

## Intent

Let the owning Feature Team, its Epic Team, and periodic review agents resolve late repair delivery through supported, auditable operations even when the original feature has entered review or completed. Preserve accepted delivery history, current approvals, validated Task work, exact revision evidence, and correct worktree ownership. A human must not need to compose internal Python calls, hand-edit lifecycle files, or manufacture an authorization event to break a recovery deadlock.

### Observed incident and evidence

The 2026-11-10 recovery of `feat_046_001` and `task_046_001_006` exposed a reproducible gap. These identities and counts are regression evidence, not production special cases.

- At 22:38:54 UTC, review health recorded `feat_046_001:review-health:review_snapshot_failed:f9fef92474d2c2cf`. `cascade/tracking.py::merge_request_snapshot` requested `headRefOid` through `gh pr view --json`; the installed CLI rejected that field. The tests had mocked a response containing the unsupported field, so they did not catch the actual query failure.
- At 22:41:26, the feature team minted Task 006 to repair the query. The feature document was already in `3_completed`, which is also used to stage a feature for review. Its first five Tasks were delivered; the new repair was not.
- PR [226](https://github.com/vincentc-b/CascadeCode/pull/226) merged into `epic/epic_046` at 22:44:32, with merge commit `23d098d071b325af554af7cf546fc1f1323cbd0c`. That accepted review did not contain the late repair. The repair's validated source was `fb1ca7f164237c9f662a8699c51849f31794c5f8`, against feature base `2c959bd71cdb0e5fe1aac053c8fc1414b096bb28`.
- Task 006 remained `merge_blocked` with `last_error=not_active`: `preflight_lifecycle_merge_target` requires an active target, while the parent feature remained completed. The queued delivery was preserved, but retries could not change that prerequisite. The durable action accumulated more than sixty attempts against the same underlying lifecycle problem.
- The feature and epic agents correctly diagnosed this. Their 22:54 and 22:56 reports in `docs/_queue/epic_046.jsonl` explicitly say that Task recovery preserves the delivery but does not clear the parent status gate, and that no feature-scoped tool exposes a safe completed-to-active transition. A 22:57 escalation and subsequent periodic reviews requested lifecycle-owner repair. The reports did not become an executable lifecycle repair; repeated team wakeups and investigation turns could only rediscover the same gap.
- During operator recovery, moving the feature back to active was reverted to backlog by the watchdog because the new active-path introduction had no matching current `FeatureReadyToPlan` authorization event. The authorization guard was enforcing its contract; the missing piece was an operation that performed the lifecycle transition and recorded authority together.
- Reopening also moved the target revision, so the old validation could not simply be reused. The existing Task was synchronized and tested again before its delivery was rearmed. The tracking and review-health suites passed all 12 tests. Two broader completion-reconciliation fixture failures reproduced on the unchanged baseline and were not evidence that the query repair was red.
- Resolving through a merged board exposed ownership ambiguity: a completed copy of `feat_046_001` in sibling `feat_046_002` could outrank the owning checkout's backlog copy. The generic preference function rewards any feature worktree, rather than the exact registered owner. An operation through the selected document root could therefore mutate the sibling's historical copy.
- After the repair merged locally and PR 226 was reconciled as merged, retiring the feature checkout removed the only visible completed document for Task 006. Its older active document in the Task checkout then resurfaced, even though its execution and queued-merge action were succeeded/completed. Operator recovery had to persist the terminal Task record on the Epic checkout before the live board truthfully showed both items completed with no recovery incident.

The operator applied the supported-CLI query repair to the running source and cleared the existing review-health action through canonical review recovery. This repaired the immediate instance; it did not implement a general late-repair lifecycle, parent recovery capability, deterministic retry routing, exact owner resolution, or descendant-safe retirement. Do not treat an operator hotfix or a successful local Task merge as proof that a later source head was reviewed and integrated into its parent.

### Existing mechanisms to extend

`mint_task` refuses a blocked feature but does not establish a recovery lifecycle when its parent is completed. `try_complete_feature` has an already-completed fast path before normal child-completion checks. Feature-child `supervise_child(recover)` primarily inspects incidents and wakes the team; it does not reconcile the completed parent. `not_active` is classified with transient merge waits. Review health uses the same running implementation that the stranded Task was trying to repair. Worktree retirement proves that the parent document exists elsewhere without proving that all required child terminal records survive.

Coordinate with the existing child-delivery work in Epics 040-042, the general lifecycle-convergence proposal in Epic 021, and Epic 044's audit presentation work. This brief closes the concrete execution and persistence gaps; it does not replace their recovery machinery or duplicate the audit dashboard redesign.

### Success criteria

1. Define an explicit contract for repair requested while a feature is active, staged in completed for an open review, or already accepted through a merged review. Minting repair work and completion/review reconciliation must not leave a new nonterminal child under a terminal parent with no executable delivery route. Preserve the distinction between a reviewed source document's location and operational terminality.
2. Provide an owner-scoped, generation-bound recovery operation usable by the Feature Team, its immediate Epic parent, and admitted audit recovery. It must inspect current parent/child status, declared ownership, exact source/target revisions, durable delivery identity, review state, blockers and execution leases. Choose a legal recovery transition or a linked follow-up feature/review; do not blindly reopen every completed feature or redispatch an already validated Task.
3. Make any reactivation transaction publish durable authority covering the active path introduction, the lifecycle state change, and an idempotent recovery identity. Handle crashes between these steps and replay after restart. The normal watchdog must recognize the result without reverting it to backlog. Retain the existing unauthorized-active detection; agents must not fabricate dispatch evidence or gain unrestricted board writes.
4. Preserve the existing Task identity, allowed worktree changes, committed implementation and validation history. If recovery advances either tested head, synchronize through the existing Task workflow, rerun the relevant final gate, and replace the validation pair only after green tests. Reject stale evidence, live execution owners, dirty/protected work, changed parent ownership and invalid approvals through the current safety boundaries. Do not mint duplicate work merely to escape a stuck status.
5. Make recovery executable rather than a team wakeup alone. A parent request or periodic investigation must select a concrete admitted operation, show its owner and acknowledgement, and verify the durable result. If the capability is absent or a persistent orchestration defect prevents execution, produce a deduplicated scoped repair handoff under an eligible owner, or an explicit operator prerequisite. A recorded repair request, message delivery or agent turn is not successful recovery. Do not spend recurring review turns reporting an unchanged actionable contradiction without progressing or escalating that handoff.
6. Classify merge refusals by the prerequisite that can change them. In particular, a completed-parent `not_active` is a deterministic lifecycle mismatch, not an ordinary transient wait such as a live turn being busy. Route it once to the accountable lifecycle owner, retain the validated delivery, and reassess only on relevant evidence/generation changes or bounded policy. Do not repeatedly spend the merge-attempt budget on the same impossible merge. Preserve all historical attempts rather than resetting them to hide the loop.
7. Preserve accepted review history and its exact source/target heads. A merged PR covering the first five Tasks cannot authorize a later repair head, close a new publication obligation, or justify deleting its only checkout. Repairs after acceptance must use the normal appropriate follow-up review/integration route, linked to the originating review, without overwriting that approval as if it covered the new code. Recheck review health only with current forge facts and distinguish Task delivery, review acceptance, integration and runtime deployment.
8. Resolve mutation ownership from the exact registered work item and canonical provenance, not just column rank or the presence of `/worktrees/feat_` in a path. A sibling worktree may contain useful historical read evidence but must not become the mutation owner of another feature. Cover preferred/returned snapshots and split product/tracking roots. Ambiguous or missing ownership must produce a typed refusal or admitted repair, never an arbitrary write to whichever copy happens to win iteration order.
9. Before retiring a parent worktree, prove that every required terminal child document and completion/provenance fact remains durably discoverable outside that checkout. Publish missing terminal records through canonical persistence or retain the checkout with an actionable reason. Preserve needed descendants, unmerged repair revisions and review obligations as well as the parent document. A stale active copy must not resurrect completed work after cleanup; terminal success must remain consistent across the board, execution ledger, delivery queue and parent rollup.
10. Keep parent completion, review reconciliation and retirement coherent with newly admitted repair children. The already-completed fast path must not skip outstanding child delivery/publication obligations simply because an older parent or review is terminal. Make replay and concurrent closeout/repair admission converge on the same outcome without losing accepted history or marking unfinished work complete.
11. Retain the verified GitHub CLI compatibility repair or its equivalent and add contract coverage that asserts the actual supported query and extraction of the pinned source SHA. Preserve merge SHA, mergeability, comments, descriptions and GitLab behavior. Exercise an actual CLI-compatible response; mocking an unsupported field is insufficient. Address the bootstrap path for repairing orchestration code that is itself needed to reconcile reviews, through supported reviewed deployment rather than arbitrary runtime imports or manual hotpatching.
12. Surface the same typed incident and next action in the child, parent and periodic review views: lifecycle mismatch versus expected execution wait, exact owner and blocked operation, validation pair, prior/required review, selected repair, freshness, and confirmed outcome. Repeated observation must not duplicate work, messages, review publications or worker turns. A resolved incident clears only after authoritative postchecks prove the relevant obligation satisfied.
13. Add end-to-end regressions using normal mint, dispatch, validation, delivery, parent supervision, review-health and watchdog boundaries. Reproduce the motivating sequence for an open review and for an already merged review, including a repair arriving concurrently with closeout. Demonstrate supported parent/audit recovery with no hand-edited ledger, manually constructed success result, fabricated event, forced status reset or duplicate Task. Repeated sweeps and worker restarts must converge on one durable repair and the correct reviewed/integrated result.
14. Test both source/target movement after validation, stale generations, live owners, dirty and missing checkouts, changed ownership, unresolved human comments, missing approvals, dependency refusals and split roots. Verify protected gates remain enforced. Include a sibling with a completed historical copy that previously outranked the real owner, and retirement where the parent exists elsewhere but its last completed child record does not.
15. Verify the full result after retirement and restart: no queued delivery or recovery incident remains falsely active, the Task execution and board agree on completion, accepted versus follow-up review evidence is accurate, and descendants remain discoverable. Record real validation evidence and any outstanding review/deployment prerequisites. A test that only wakes a team or changes one status does not satisfy acceptance.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use Codex as this epic's default provider and preserve the explicit role model and reasoning settings in this brief for descendants. Do not change workspace-wide provider defaults. File this as a backlog brief for normal PR approval and activation; implementing the requirements or activating teams is outside this filing.

Reuse the existing lifecycle, Task delivery, ownership, review, authorization, audit and worktree persistence boundaries. Introduce the smallest coherent recovery capability and typed handoff needed for the failure, rather than a second scheduler, parallel queue, unrestricted lifecycle editor or new review system. Document the chosen state model and actor permissions before implementation.

Keep canonical fresh-generation admission and execution-lease checks at every mutation boundary. UI or audit read snapshots must never authorize a repair. Preserve human plan/revision approval, comment resolution, software installation, credential and forge-review gates. A genuine missing external permission remains an explicit external prerequisite.

Do not discard dirty work, reset an attempt counter, delete historical recovery receipts or claim a merged historical PR approved subsequent repair commits. Retain original and successor action/review identities, validation generations, ownership, requests, refusals, acknowledgements and postcheck evidence. Cleanup must not be used as a substitute for fixing the state contradiction.

The initial query defect has an existing tested Task implementation. Inspect the current code and delivery history before creating new repair work; do not reimplement or claim it as a newly discovered feature. Keep unrelated UI loading optimizations and audit dashboard presentation outside this epic, except for the minimal incident/recovery contract it must expose.

Likely boundaries: `cascade/feature/mint.py`; `cascade/boss/rollup.py` and `merge.py`; `cascade/workspace/branch_synchronization.py`, `integration_worktree.py` and `doc_root.py`; `cascade/watchdog/loop.py`, audit admission/recovery/investigation modules and event authorization; `cascade/task_rollup.py`, Task final validation/action recovery; `cascade/team_supervision.py`, Epic/Feature recovery adapters; `cascade/review.py`, `review_health.py`, `tracking.py`; and the existing board/War Room projections and lifecycle integration tests. These are investigation entry points, not a mandate to edit every file.

Record requirements interpretation, exact mutation authority, crash ordering, owner resolution, validation freshness, accepted/follow-up review semantics, descendant durability, retry policy, deployment handoff and verification limits in the appropriate design records and commits. Preserve compatibility with existing durable ledgers and explain any migration of legacy contradictory state.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which reviewed recovery route applies before versus after the originating feature review has merged, and when does changed scope require renewed human approval?
- How will orchestration repair reach the running supervisor through supported deployment when the old implementation blocks the workflow needed to deliver it?
- Which durable ownership and descendant-completion evidence must survive a parent checkout's retirement, including legacy state with conflicting copies?
- How does an unavailable repair capability become executable scoped work or an explicit operator prerequisite without an endless investigation loop?

## Decision log

- 2026-11-10 · Human · Requested this incident-based brief; approval is pending PR review and merge.

## Amendment log

_(none)_
