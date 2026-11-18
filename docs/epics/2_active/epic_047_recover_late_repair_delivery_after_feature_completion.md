---
id: epic_047
title: Recover late repair delivery after feature completion
tier: epic
status: active
parent: null
children:
- feat_047_001
- feat_047_002
- feat_047_003
- feat_047_004
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-10'
updated: '2026-11-18'
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

### Planning baseline and scope

The existing implementation confirms the incident's underlying gaps: `mint_task` has no completed-parent repair admission; `_try_complete_feature` returns through its completed fast path before ordinary child gates; `task_rollup` classifies `not_active` with transient waits; Feature-child `supervise_child(recover)` sends a message and wakes a team; `_meta_preference` rewards generic feature worktree paths; and retirement checks the parent document without a complete descendant durability proof. These are scoped changes to the existing supervisor, durable actions, review workflow and repository boundaries.

The GitHub query repair is already in `cascade/tracking.py::merge_request_snapshot`: it requests `commits`, extracts the final commit OID, and does not request `headRefOid`. Preserve it and strengthen actual CLI contract evidence. The supplied incident is regression context, not permission to mutate that historical work. A historical-evidence request for the motivating Task was refused as outside this team's scope; no inaccessible work record or review has been treated as inspected.

This plan uses four delivery slices and roughly ten to twelve cohesive Tasks. Child teams may consolidate Tasks where one integration test covers the invariant. There is no new scheduler, queue, audit dashboard, general lifecycle-convergence rewrite, automatic package installer or blanket completed-work reopener.

### Recovery and review state contract

Accepted review evidence is independent of a work document's current column. A repair has a durable generation/obligation; an older acceptance remains immutable history.

| Current authoritative state | Admitted route | Completion/publication requirement |
|---|---|---|
| Active Feature | Ordinary Task admission/delivery with current gates | Current children and review obligations must be satisfied. |
| Completed-path Feature staged for an open review | Admit an in-scope repair generation and authorize reactivation of the same Feature | Revalidate affected source/target pair, deliver the existing Task, update the open review through the normal publication gate, and check its actual accepted heads. |
| Feature accepted by a merged review | Preserve acceptance; conditionally admit an in-scope repair generation of the same Feature | Create a distinct follow-up publication linked to the prior review; the historical merged callback cannot close the later obligation. |
| Unknown/conflicting owner or review facts; material change outside approved scope | Typed refusal, existing amendment/corrective-work path or explicit operator prerequisite | Current human approval and authoritative evidence are prerequisites, never inferred from old acceptance. |

The accepted-work route preserves the same Task identity, source checkout, allowed changes and validation history. A follow-up Feature is reserved for a materially different approved scope; it is not an automatic escape hatch for a stranded Task. Do not automatically reparent or duplicate the Task.

The durable repair progression is request/admission → authority prepared → parent delivery enabled → validation/delivery → current review obligation → parent integration → descendant-safe retirement → verified resolution. These are recovery-action phases, not a second filesystem status vocabulary. A failed prerequisite retains the operation and evidence with a typed owner/action. Recovery success is the authoritative postcondition, not an acknowledgement or a worker turn.

### Mutation authority, persistence and replay

One canonical operation, exposed through scoped Feature self-recovery, immediate Epic recovery and admitted audit adapters, inspects work/parent IDs, registered owner, branch/root provenance, repair generation, action identity, current source/target heads, validation pair, review identities/heads, plan/revision approvals, comments, dependencies and live execution leases. Read projections may describe this operation but cannot authorize it.

Use the existing lifecycle lock and durable action/claim machinery. Persist a replayable intent and operation-specific authority binding before introducing an active document path. The watchdog must validate the corresponding receipt/generation and path introduction; retain ordinary unauthorized-active detection. Do not fabricate `FeatureReadyToPlan` dispatch evidence. The Architect must specify the exact receipt/event binding and lock ordering before sign-off.

At every mutation and resumed phase, re-read ownership, generation, heads and relevant gates. A crash before authority causes no active introduction; a crash after authority or move resumes the same transaction; a changed owner/head/approval yields a refusal or existing resynchronization route, not a destructive rollback. Keep original and successor action/review identities and every historical attempt. The implementation must define compatibility handling for legacy contradictory states without inventing missing acceptance.

Any source or target movement invalidates reuse of the old validation pair. Synchronize and rerun the existing Task final gate, then replace current evidence only after green validation. Do not redispatch an unchanged validated implementation merely to change lifecycle status.

Repair admission, minting, closeout and retirement must serialize their shared prerequisites. Outstanding children and publication obligations gate every closeout path, including the current already-completed branch. A historical merged callback cannot override a new obligation.

### Exact ownership and retirement

Mutation roots come from the exact registered work item and canonical parent/provenance, with product/tracking separation. Historical sibling copies are read evidence only. Missing/conflicting ownership must be actionable and fail closed unless an existing admitted owner-repair operation proves the destination.

Before removing a parent checkout, inventory required terminal descendants and their completion/delivery provenance, verify they remain discoverable in the authorized surviving root, canonically persist missing terminal records, and re-read the result. Refuse retirement while dirty/protected work, a needed descendant, an unmerged repair head or a current review obligation remains. Accepted review evidence must cover the current obligation; a generic merge-confirmed Boolean is insufficient proof for a later head. Repeated sweeps and restart must not resurrect stale active child copies.

### Deterministic routing and executable handoff

A completed-parent `not_active` is a lifecycle mismatch; live-owner `busy` remains an execution wait. Preserve the Task delivery and route the mismatch once per meaningful generation to its accountable owner. Reassess on relevant owner/head/review/approval/lease/repair-result changes, with bounded fallback policy; unchanged sweeps must not spend the merge-attempt budget or start repetitive investigation turns.

Feature, parent and audit requests converge on the same admitted operation. A missing capability or persistent orchestration defect produces one scoped repair handoff under an eligible owner, or an exact operator prerequisite where no authorized executor exists. Track request, acknowledgement, execution and postcheck separately.

Expose a shared typed incident containing the blocked operation/owner, generation, validation pair, prior and required review, selected repair, freshness and verified outcome. Preserve existing bounded audit projection/read interfaces and add only the fields needed for this workflow.

### Reviewed runtime handoff

Task delivery, forge acceptance, parent integration and runtime deployment are separate facts. If the running supervisor cannot execute a needed reconciliation, retain the repair and expose a handoff naming the reviewed source revision, expected runtime revision, supported drain/stop/start path and post-restart checks. Updating installed software still needs exact current human installation authority. No arbitrary runtime imports, manual ledger/event edits or hotpatching. The final feature owns a tested operator runbook using existing deployment controls; a new deployment platform is outside scope.

### Diagram-impact inventory and ownership

Authoritative model: `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{workspace.dsl,model.dsl,views.dsl,workspace.contract.json}`. Accepted render/review snapshots remain immutable. Proposed view keys below must be authored against real implementation symbols and validated before plan sign-off; they are not claims of current implementation.

| Level / view keys | Owning designs and source entry points | Required work / owner | Verification and current result |
|---|---|---|---|
| Landscape/context: `cascade-landscape`, `cascade-context` | `DESIGN.md`; supervisor, operator, forge and provider boundaries | Epic Architect verifies unchanged topology: repair stays inside existing local supervisor/forge responsibilities, no new external actor/service. | Source contract valid; final diff must justify any no-change result. |
| Containers: `cascade-containers` | Root and `cascade/DESIGN.md`; supervisor, repository, War Room | Architect verifies unchanged runtime/data boundaries; describe recovery/action persistence without implying process isolation. | Existing view valid; verify repair state uses current stores and no new deployable container. |
| Components: `cascade-supervisor-components`, `cascade-team-components` | Package plus Workspace, Boss, Feature, Watchdog, Epic and Task designs | All feature owners update collaboration/authority edges; Architect integrates cross-boundary ownership. | Review normal admission/delivery and failed recovery/restart against code; pending. |
| Code: proposed `cascade-workspace-code`, component `element.component.workspace` | Workspace design; `integration_worktree.py::{merged_board,_meta_preference,retire_integration_worktree,terminal_doc_persisted_outside_worktree}`, `doc_root.py::resolve_doc_worktree` | `feat_047_001`: exact owner selection and descendant persistence/removal gates. | Current model has no Workspace Code view: material pre-sign-off coverage gap assigned to Architect, implementation reconciliation to feature. |
| Code: `cascade-feature-code`, `cascade-task-code`; proposed `cascade-boss-code`, component `element.component.boss` | Feature/Task/Boss/package designs; `mint_task`, `try_complete_feature`, branch preflight, final validation, review/merge entry points | `feat_047_002`: add actual admission, delivery, review-obligation and closeout collaborators; document crash sequence and state owner. | Existing team views cover graph plumbing, not full repair lifecycle; Boss Code view absent. Architect must establish source-linked coverage before sign-off. |
| Code: `cascade-epic-code`, `cascade-teams-code`; proposed `cascade-watchdog-code`, component `element.component.watchdog` | Epic/Watchdog/package designs; `team_supervision.py::supervise_child`, `epic/recovery.py::recover_feature`, `task_rollup.py`, `audit_recovery.py::dispatch_audit_recovery`, `loop.py::_event_authorizes` | `feat_047_003`: admission, claim, routing, receipt-authority and postcheck collaborators; minimal projection consumer implications. | Watchdog Code view absent; pending actual source contract and normal/failure navigation verification. |
| Supplementary behavior | Workspace, Feature, Boss, Task, Watchdog designs | Respective owners author owner-resolution/retirement flow and repair-admission/authority/revalidation/review/restart sequences; package links cross-boundary flow. | Trace one normal and one crash/refusal/resume scenario for each affected significant subsystem. |
| Integrated UI and performance | Workspace and War Room designs; model/source contract and existing renderer/browser boundary | `feat_047_004` verifies all delivered views and affected design links. | Real context→container→component→Code, Level up, deep-link restoration, pinned source, stale symbols and component ownership; cold/warm timing and artifact reuse required, not yet run. |

Each significant Code view uses `cascade.codeComponent`; each node carries matching `cascade.parent`, confined `cascade.sourcePath`, and a real `cascade.sourceSymbol`. Model and contract updates must land together. Keep one bounded batch render, existing resource limits and warm artifact reuse. Supplementary Mermaid cannot substitute for integrated Code navigation.

Requirement ownership proposed for implementation: Workspace owns `REQ-WORKSPACE-OWNER-001` and `REQ-WORKSPACE-RETIRE-001`; Feature owns `REQ-FEATURE-REPAIR-001` and `DEC-FEATURE-REPAIR-001`; Boss owns `REQ-BOSS-CLOSEOUT-001`; package owns `REQ-REVIEW-REPAIR-001` and `REQ-CASCADE-RECOVERY-001`; Watchdog owns `REQ-WATCHDOG-REPAIR-001`. The Architect must establish these anchors and link consumers before sign-off, preserving existing `REQ-BOARD-001`, `REQ-TASK-001`, `DEC-TASK-001` and approval/architecture requirements. Do not duplicate requirements across designs.

## Cross-module constraints

Use Codex as this epic's default provider and preserve the explicit role model and reasoning settings in this brief for descendants. Do not change workspace-wide provider defaults. The human has activated this epic. This turn authorizes planning and backlog feature creation; implementation dispatch remains subject to the normal epic plan approval and dependency gates.

Reuse the existing lifecycle, Task delivery, ownership, review, authorization, audit and worktree persistence boundaries. Introduce the smallest coherent recovery capability and typed handoff needed for the failure, rather than a second scheduler, parallel queue, unrestricted lifecycle editor or new review system. Document the chosen state model and actor permissions before implementation.

Keep canonical fresh-generation admission and execution-lease checks at every mutation boundary. UI or audit read snapshots must never authorize a repair. Preserve human plan/revision approval, comment resolution, software installation, credential and forge-review gates. A genuine missing external permission remains an explicit external prerequisite.

Do not discard dirty work, reset an attempt counter, delete historical recovery receipts or claim a merged historical PR approved subsequent repair commits. Retain original and successor action/review identities, validation generations, ownership, requests, refusals, acknowledgements and postcheck evidence. Cleanup must not be used as a substitute for fixing the state contradiction.

The initial query defect has an existing tested Task implementation. Inspect the current code and delivery history before creating new repair work; do not reimplement or claim it as a newly discovered feature. Keep unrelated UI loading optimizations and audit dashboard presentation outside this epic, except for the minimal incident/recovery contract it must expose.

Likely boundaries: `cascade/feature/mint.py`; `cascade/boss/rollup.py` and `merge.py`; `cascade/workspace/branch_synchronization.py`, `integration_worktree.py` and `doc_root.py`; `cascade/watchdog/loop.py`, audit admission/recovery/investigation modules and event authorization; `cascade/task_rollup.py`, Task final validation/action recovery; `cascade/team_supervision.py`, Epic/Feature recovery adapters; `cascade/review.py`, `review_health.py`, `tracking.py`; and the existing board/War Room projections and lifecycle integration tests. These are investigation entry points, not a mandate to edit every file.

Record requirements interpretation, exact mutation authority, crash ordering, owner resolution, validation freshness, accepted/follow-up review semantics, descendant durability, retry policy, deployment handoff and verification limits in the appropriate design records and commits. Preserve compatibility with existing durable ledgers and explain any migration of legacy contradictory state.

## Core dependencies

Canonical dependency manifest revision **4** is ready: all 14 read-only checks succeeded with current evidence. It declares the existing local host `ip-172-31-37-14`, Linux/x86_64, host sandbox, Python runtime `/opt/conda/bin/python3.12`, repository/check-executor root `/home/ubuntu/dev/CascadeCode`. This is the selected local verification environment; implementation edits remain in the owned epic worktree and child worktrees. No remote deployment target is asserted.

Declared exact installations: Python 3.12.8; PyYAML 6.0.3; cursor-sdk 1.0.37; langgraph 1.2.14; langgraph-checkpoint-sqlite 3.1.1; pytest 9.0.3; setuptools 80.9.0; Playwright 1.64.0 and Chromium 156.0.8078.4; Git 2.34.1; gh 2.4.0+dfsg1; Docker 28.0.0; Codex CLI 0.169.0; and Structurizr digest `sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`. Local file/installed metadata hashes bind observations; they do not attest original upstream package provenance. The pinned renderer digest comes from `cascade/workspace/c4_render.py`.

No installation or upgrade is requested or authorized. GitLab behavior is checked at the existing adapter contract; a live GitLab exercise would require its separately declared CLI/environment. Forge credentials, human review and runtime deployment remain external gates, not claims established by a version check. Add any newly required software to the canonical manifest before using it.

Extend the existing child-delivery/recovery code already present; do not make inaccessible historical epics implicit prerequisites or duplicate their scheduler/audit machinery. Feature dependencies are the executable sequence below.

## Feature breakdown

| Feature | Scope and success-criteria ownership | Depends on | Indicative Task budget |
|---|---|---|---|
| `feat_047_001` — Resolve exact work owners and preserve descendants before retirement | Criteria 8–9; durability portion of 15. Exact mutation owner, split roots, terminal descendant persistence and conservative retirement. | None | 3 |
| `feat_047_002` — Admit late repair generations without losing accepted review history | Criteria 1–4, 7, 10. Canonical authority transaction, same-Task preservation/revalidation, open/follow-up review and closeout interlock. | `feat_047_001` | 3–4 |
| `feat_047_003` — Execute lifecycle mismatch recovery through parent and audit supervision | Criteria 5–6, 12. Deterministic routing, executable scoped adapters, deduplicated handoff and shared typed incident/postchecks. | `feat_047_002` | 2–3 |
| `feat_047_004` — Prove late repair convergence and document reviewed runtime handoff | Criteria 11, 13–15. Existing CLI fix preservation, end-to-end lifecycle/race/restart proof and supported deployment prerequisite. | `feat_047_003` | 2 |

All four backlog specs have been persisted through `mint_feature`; no feature execution was requested. Each contains explicit design/model ownership and mandatory Task acceptance coverage. Preserve the epic's provider/model/reasoning overrides in descendants.

### Verification strategy

Focused owner tests belong with implementation. Use a shared production-boundary integration matrix for active, open-review and merged-review repair plus concurrent closeout. Exercise normal mint/dispatch/validation/delivery, Feature/Epic/audit recovery and watchdog authorization; deterministic forge transport may model remote acceptance but may not synthesize internal lifecycle success. Include changed source/target heads, stale generation/owner, live leases, dirty/missing checkout, comments/approvals/dependencies, split roots, misleading sibling copies and missing external child records. Avoid a full cross-product of redundant unit cases.

Final acceptance requires restart and repeated sweeps to converge on one repair; immutable prior review plus correctly pinned follow-up acceptance; no false active delivery/incident; and consistent board/execution/queue/rollup after retirement. Bound conflict-publication checks to the configured safeguard command. Record actual tests and baseline failures; do not report local validation as production deployment.

### Planning review evidence and remaining work

Reviewed source/design boundaries: root `DESIGN.md`; `cascade/DESIGN.md`; Feature, Boss, Workspace, Board, Task and Watchdog designs; existing C4 model/views/contract. No DESIGN.md or model edit has been made in this manager turn, because these documents must describe verified current code and the Architect must establish the missing integrated structure before sign-off. Proposed behavior and requirement allocation remain in this work record and child plans.

Actual checks: `python -m pytest -q tests/test_tracking_find.py tests/test_review_health.py` — **13 passed in 5.67s**. `validate_c4_workspace(Path("architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5"))` — valid source contract. Existing pinned Docker image inspected; installed Chromium launched and exact version checked. No real architecture render, UI navigation, new recovery scenario or deployment has been claimed.

Material pre-sign-off work assigned to the Epic Architect: finalize exact receipt/event/lease/lock ordering and review-generation schema; author source-linked implementation coverage and required Code views; establish unique requirement/decision anchors and cross-links; inspect affected Epic/War Room consumer interfaces; reconcile stale attribution/gap prose in changed designs; validate/render and record navigable coverage and limits. Then both roles review the same final epic revision. Manager sign-off is intentionally pending this work; do not treat a valid model syntax check as architecture completeness.

## Open questions

Product scope choices are resolved by the state/authority and feature contracts above. The following architectural details remain blocking for plan sign-off and are assigned to the Epic Architect:

- Specify the operation-specific authority receipt/event schema and exact crash-safe ordering recognized by the watchdog, including generation and active-path bindings.
- Specify how current and historical review identities/heads coexist in the existing durable review/action stores and how legacy contradictory records fail closed.
- Specify the exact owner-resolution and descendant-survival proof interfaces, lock ordering and authorized persistence destinations for split roots.
- Confirm which existing supported controls perform the reviewed runtime handoff; name any unavoidable operator prerequisite without granting deployment/install authority.
- Complete the diagram-impact inventory's missing integrated Code views, source-linked design contracts, rendering/navigation evidence and semantic design review.

## Decision log

- 2026-11-10 · Human · Requested this incident-based brief; approval is pending PR review and merge.

## Amendment log

_(none)_
