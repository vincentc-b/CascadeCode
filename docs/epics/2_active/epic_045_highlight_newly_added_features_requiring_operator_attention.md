---
id: epic_045
title: Explain feature activation requirements and highlight newly added work
tier: epic
status: active
parent: null
children:
- feat_045_001
- feat_045_002
- feat_045_003
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

Two features deliver complete user-facing slices. Keep activation eligibility, operational attention and lifecycle status separate.

### Activation explanation boundary

Extend the canonical Python evaluation and serialization path, principally `cascade/feature/readiness.py`, `cascade/stacked_dispatch.py`, dispatch/Boss refusal evidence and `cascade/war_room/serialize.py`. Existing `approved` and `blockers` consumers remain compatible. Add a versioned explanation object containing summary state, primary reason, all reasons, satisfied prerequisites, evaluation time/snapshot identity, evidence freshness and optional last actual dispatch attempt. Each reason carries a stable code, readable explanation, owner (operator/other work/system), affected work IDs, available existing actions/review links, and its evidence source/freshness. Feature planning pins the exact field names and source map before task execution.

Use the same canonical predicates at explanation and action boundaries. Extract sibling identities from `epic_blocks_feature_dispatch` and related merge predicates rather than reimplementing serial/stacked rules. Dependencies retain the existing canonical projection; unknown dependency evidence is not satisfied. Approval includes revision-bound review requirements, not merely a timestamp. Provider compatibility uses the existing bounded inventory snapshot; action-time preflight remains authoritative. Parent state, review threads, merge state and dispatch-base selection keep their existing owners.

Primary-summary ordering: a current actionable human blocker comes first; otherwise missing/stale required evidence yields readiness unavailable; otherwise a current work/system blocker yields waiting; only a complete, current passing evaluation yields ready awaiting dispatch. Preserve all additional reasons, including uncertainty, behind expansion. Use a stable source-code/work-ID ordering within those groups. Passing gates never means running. An actual refusal retains its attempted-at evidence and actionable details; distinguish it from a newer readiness evaluation rather than allowing a stale refusal to masquerade as the current blocker. Do not promise a start time.

Acquire reusable evidence once per board response. Reuse cached provider and dispatch-base evidence; do not add discovery, Git probes or per-row expensive checks to browser polling. Missing cached facts surface as unknown/rechecking. Record attempts only at actual dispatch boundaries. Explanation reads do not dispatch, mutate lifecycle state, or grant any authority.

### Attention state and acknowledgement boundary

Use stable feature ID within the canonical tracking workspace as identity. Store versioned durable attention records independently of plan content and lifecycle, with creation/discovery provenance, rollout baseline, acknowledgement actor/time and a monotonic state revision. Reuse existing atomic persistence/process-lock conventions; all managed worktrees and split product/tracking roots must resolve the same tracking-owned state. No acknowledgement file belongs in the product repository or in transient browser-only state.

New creation registration consumes canonical `FeatureMinted` evidence, with idempotent reconciliation for legitimately discovered IDs not present in the ledger. A durable first-discovery record is provenance for that fallback, not a heuristic over filenames, order, mutable dates or status. Register baseline/discovery through startup/mint/reconciliation boundaries; GET, rendering and expansion never acknowledge. Replayed events and already-known IDs cannot reset an acknowledgement.

Choose workspace-shared acknowledgement for the current local-operator deployment, and disclose that scope. The existing `HumanIdentityVerifier` authenticates explicit Mark seen and supplies the recorded actor; no new accounts or unauthenticated write endpoint. Mark seen is idempotent and clears only attention. Approval does not implicitly acknowledge in this slice. Reject invalid/unauthorized writes; preserve acknowledgements under concurrent requests and out-of-order poll responses. A corrupt/unavailable ledger is an unavailable attention projection, not permission to reset the baseline.

On first rollout, atomically record all known feature identities. Mark currently open backlog/ready-to-plan features under active, non-cancelling epics unseen, regardless of approval; this captures pending corrective additions without resetting approvals. Other preexisting features form the historical baseline and receive no New badge. Persist the rollout marker so restarts cannot rerun bootstrap. Features created after that baseline remain unseen until explicit acknowledgement. Exclude completed/cancelled/retired work from pending-attention aggregates while retaining provenance and prior acknowledgement. Returning an existing identity to backlog or revising its plan must not recreate newness.

### Presentation and acceptance

Render the canonical activation summary/actions in normal board views, with expandable secondary blockers and satisfied prerequisites. Reuse the dependency display and existing review/provider controls. Feature rows show accessible New text separately from lifecycle; collapsed epic rows show an aggregate with a keyboard-operable reveal/navigation action. New work displays its actual next action, including a normal scheduler wait when already approved. Keep updates stable, readable and quiet.

Use focused backend/API integration tests for gate parity and attention invariants, lightweight existing Node UI cases where useful, and a real-browser journey for the motivating discovery/approval workflow. Reuse `tests/war_room/test_board_feature_readiness.py`, `test_provider_readiness_projection.py`, `test_late_mint_feature_approval_e2e.py` and `tests/test_stacked_dispatch_integration.py` as relevant. Feature 001 verifies the approved-008/waiting-for-009 transition, all blocker families, stale/unavailable evidence and real refusal freshness; Feature 002 verifies bootstrap/replay/restart/concurrency/split roots and the two-corrective-feature journey. Assertions must show that reads/acknowledgement cannot change approvals, blockers, lifecycle or scheduling policy. Do not add a separate testing feature or redundant unit suites.

## Cross-module constraints

Use Codex as this brief's default provider and preserve explicit role defaults for descendants. Do not change the workspace-wide provider configuration. File this as a backlog brief for normal review and activation; do not implement it while filing.

Keep the change focused on explaining feature activation requirements and discovering new work. Do not redesign the audit dashboard, implement automatic approval, change serial/stacked dispatch policy or task scheduling, or merge unfinished feature work. Coordinate with epic_044's separation of current problems, coverage and history without making this small feature depend unnecessarily on that larger redesign.

Likely areas: cascade/feature/readiness.py, cascade/stacked_dispatch.py, Boss/dispatch refusal projections, War Room board serialization, static/war_room.js and associated templates/styles, existing feature creation metadata and operator-state persistence. Extend the authoritative readiness projection with blocker identities rather than reverse-engineering them from UI labels. Inspect existing identity and acknowledgement conventions before choosing storage. Document the readiness/explanation contract, source of each blocking fact, creation identity, acknowledgement ownership, bootstrap behavior, approval separation and validation in the design and commit messages.

Additional validation: reproduce 034_008 approved + dependencies satisfied + supported provider + active sibling 034_009, then transition the sibling to completion and confirm the explanation changes according to fresh readiness without an extra approval. Cover multiple simultaneous blockers, pending review versus active execution, an inactive parent, changed-plan approval, unavailable evidence, valid empty blockers awaiting scheduler dispatch, and an actual dispatch refusal. Verify that explaining or acknowledging a reason does not bypass the canonical gate or alter scheduling policy.

## Core dependencies

Dependency manifest revision 1 was declared before planning changes and automatically verified successfully on 2026-11-12. It declares existing prerequisites, not an empty/no-software decision, and grants no installation authority.

Local validation target: host `ip-172-31-37-14`, Linux x86_64, repository/check-executor root `/home/ubuntu/dev/CascadeCode`, runtime `/opt/conda/bin/python3.12`, host sandbox, no container. The owned implementation worktree is `/home/ubuntu/dev/CascadeCode/.cascade/worktrees/epic_epic_045`; its code checks run there. The manifest identifies the host-level verification executor, not a production deployment target.

Verified installed versions: Python 3.12.8; PyYAML 6.0.3; cursor-sdk 1.0.37; langgraph 1.2.14; langgraph-checkpoint-sqlite 3.1.1; pytest 9.0.3; Git 2.34.1; Node 20.20.2; Playwright 1.64.0 and its Chromium 156.0.8078.4. The manifest pins executable or installed-distribution RECORD digests and read-only verification recipes. Python project requirements come from `pyproject.toml`; Node and Playwright/Chromium support existing UI/browser validation patterns. Chromium launch was verified. These are local installed-artifact fingerprints, not claims about upstream download provenance. No package installation, upgrade, new runtime service or production infrastructure is required by this design.

Feature 002 depends on Feature 001's canonical explanation/actions. Neither feature depends on epic_044; preserve compatibility with its separation of present problems and history through additive projections and focused shared-file review. The 034 IDs and PR reference are regression fixtures, not live dependencies or targets for modification. Preserve inherited Codex role/model/reasoning defaults; do not alter workspace provider configuration.

## Feature breakdown
- feat_045_003

| Feature | Shippable outcome | Depends on | Epic criteria |
| --- | --- | --- | --- |
| feat_045_001 — Explain feature activation readiness and actual dispatch waits | Canonical structured reasons, sibling identities, freshness/refusal evidence and board UI with next actions | None | 1–5; activation-specific validation and accessibility |
| feat_045_002 — Highlight newly added features with durable explicit acknowledgement | Durable discovery/seen state, conservative rollout, authenticated Mark seen, collapsed counts and complete operator journey | feat_045_001 | 6–16; consumes 001 for criterion 8 |

Features 001 and 002 are backlog product plans with explicit acceptance scope. Child teams refine schemas/tasks within these contracts after normal approval/dispatch; neither minting nor this plan approves or starts them. Integrate and validate 001 before 002 so new-feature UI consumes the real explanation contract. Each feature includes its own tests and documentation; no third integration-only feature.

### Audit-discovered publication repair

`feat_045_003` — Repair architecture publication for owned planning worktree lineage — is a separately scoped backlog orchestration repair, with no dependency on 001/002. It restores publication of this epic's committed architecture review before trunk integration. It is not a third product or integration-only slice; the two user-facing slices and their acceptance scope remain unchanged.

Investigation `investigation_4ca123bb9bd945fb98958705e01035af` confirmed the original missing-document-revision evidence is no longer reproducible: a fresh bounded canonical audit read found plan `48c4ce6`, owned HEAD `d6148184`, no evidence errors and `expected_wait / plan_approval`. The persistent separate failure is architecture publication `architecture-publication-8c50299f2d09024614cc747b5675c39fee6fd8faefa3622c2aa3b8c9a193e936`, superseded with `artifact_changed` because validation used tracking trunk history rather than the owned planning lineage. The exact old proposal and design commit `470b4063` remain recovery evidence; any later publication must pin the then-current plan revision rather than reuse an outdated approval or proposal blindly.

Feature 003 must assign a bounded SWE repair after normal approval, preserve revision/digest/ownership and destination checks, cover colocated and split roots, and provide supported retry of terminal publication failures without editing ledgers. Tests and review publication belong to that repair. Accepted code and a successful authorized Epic Architect publication retry are required before calling the publication defect fixed. No installation or approval bypass is authorized. Existing verified prerequisites suffice.

Adding this repair renews the epic plan review requirement. Epic Manager and Epic Architect must sign the final revised plan; human approval remains outstanding. Product implementation has not started. Audit timeouts remain historical observations, not evidence that this expected approval wait is a stuck implementation.

## Open questions

No unresolved product-scope choice blocks Epic Manager review. Resolve implementation detail within the following explicit constraints before the respective feature starts coding:

- Feature 001 must publish its fact-source/freshness table and verify parity with the actual dispatch predicates, especially serial versus stacked review waits and revision-bound approval. Unknown evidence remains unknown; lack of a cache is not grounds to run heavy probes per poll.
- Feature 001 must locate existing attempt/refusal evidence and extend the actual boundary minimally if needed; no speculative dispatch, historical-refusal-as-current behavior, or change to scheduling policy.
- Feature 002 must pin tracking-root resolution, atomic bootstrap/reconciliation and acknowledgement concurrency before implementation. Test a mint concurrent with first bootstrap and stale polling after acknowledgement; a baseline must not lose new additions or reset seen records.
- Epic Architect reviews these boundaries and the current plan revision independently. Any material contract change requires updating this epic and renewing affected sign-offs before approval.

## Decision log

- 2026-11-10 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-12 · Epic Manager · **Feature breakdown**
  Chose Deliver two complete slices: feat_045_001 for authoritative activation explanations and board UI, then feat_045_002 for durable new-work discovery and acknowledgement using 001's action contract..
  Rationale: Each slice has a visible user outcome and owns its own regression coverage. The single dependency prevents duplicate next-action logic; no separate plumbing/test-only feature or unnecessary epic_044 dependency.
  Honors: Epic success criteria 1–16; minimal scope, unchanged approval and scheduling boundaries..

- `dec_002` · 2026-11-12 · Epic Manager · **Macro-architecture**
  Chose Keep activation summaries additive to canonical readiness, distinguish fresh human action, unknown evidence, external waits and ready-awaiting-dispatch, and retain actual sibling/refusal identities without changing scheduling gates..
  Rationale: Current readiness contains string blockers and drops sibling identity; provider evidence is already cached. Shared predicates and explicit freshness explain the 034_008/009 case without inventing dependencies, approvals or start promises.
  Honors: Success criteria 1–5; canonical gate reuse, bounded polling, serial/stacked compatibility..

- `dec_003` · 2026-11-12 · Epic Manager · **Macro-architecture**
  Chose Use workspace-shared durable attention keyed by stable feature identity, authenticated explicit Mark seen with actor provenance, and a one-time baseline that exposes pending backlog under active epics while suppressing historical work..
  Rationale: The current authentication identifies a local operator rather than separate viewer accounts. Shared state matches that deployment, survives restart/replay and avoids adding accounts. Explicit acknowledgement stays independent of approval; conservative rollout captures pending corrective additions without historical badge floods.
  Honors: Success criteria 6–16; split-root ownership, approval separation, deterministic bootstrap and accessible quiet UI..

- `dec_004` · 2026-11-12 · Epic Manager · **Core dependencies**
  Chose Declare and verify the existing local Python, Git, Node and browser-test prerequisites in manifest revision 1; use the observed host deliberately as the local-check target, not as a deployment assumption..
  Rationale: All ten exact installed prerequisites passed automatic checks, including browser launch. The design extends existing Python/static-JavaScript infrastructure and needs no new installation or external service. Preserve exact inherited Codex defaults.
  Honors: Dependency declaration before planning, full target identity, no installation authority inferred from verification..
## Amendment log

_(none)_
