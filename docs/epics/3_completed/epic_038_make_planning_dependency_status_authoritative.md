---
id: epic_038
title: Make planning dependency status authoritative
tier: epic
status: completed
parent: null
children:
- feat_038_001
- feat_038_002
- feat_038_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-06'
updated: '2026-11-07'
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
# Make planning dependency status authoritative

## Intent

Planning agents must evaluate `depends_on` through Cascade's authoritative merged-board and lifecycle state, not by attempting to read another team's scoped specification. A denied content read must remain an authorization boundary and must never be interpreted as an incomplete or unaccepted dependency. Fix planning context, status reporting, and tests so activation, planning, sign-off, and operator-facing explanations agree on whether dependencies are satisfied.

### Success criteria

1. Epic and feature planning receives a minimal, read-only dependency-status projection for every declared dependency: work ID, tier, canonical lifecycle status/column, completion evidence, and a stable status-unavailable reason when authoritative state cannot be read.
2. The projection is derived from the same merged-board/lifecycle rules used by dispatch and activation. A completed item in `3_completed` satisfies the dependency even when the caller is not authorized to read its plan body.
3. Content authorization remains unchanged. Dependency status does not expose another team's plan, comments, prompts, secrets, or arbitrary repository files.
4. Planning agents and generated summaries distinguish `content_access_denied`, `dependency_unmet`, and `dependency_status_unavailable`; they never convert one into another or add a false blocker.
5. Plan readiness, feature minting guidance, War Room status, and planning transcripts report the same current dependency result. Historical messages remain historical and do not masquerade as live status.
6. A dependency that changes during a planning turn is rechecked at the sign-off/approval/minting boundary; stale evidence cannot authorize downstream work.
7. Regression coverage includes: completed dependency with unreadable spec, readable but incomplete dependency, missing dependency, tracking-repository dependency, and a dependency completing while its dependent epic is active.
8. The epic_034/epic_036 sequence is captured as a regression fixture: epic_036 completion is recognized without granting epic_034 access to epic_036's spec.

## Macro-architecture

### One authoritative read model

Resolve the configured tracking root and use the existing merged board and lifecycle predicates. Centralize duplicated dependency-completion checks behind a shared evaluator; do not create a second database. The canonical completion condition is status `completed` in column `3_completed`. Existing review, merge, and stacked-dispatch restrictions remain separate action eligibility checks and must not be weakened.

Return one allowlisted row per declared dependency: work ID, tier when known, canonical lifecycle status and column when known, outcome, safe completion evidence, and a stable unavailable reason where applicable. Attach observation time and an opaque source revision/fingerprint so consumers can identify a snapshot; these are evidence, not authorization tokens. Do not serialize plan bodies, comments, prompts, repository paths, raw exceptions, or secrets.

| Authoritative observation | Dependency outcome |
| --- | --- |
| Completed in `3_completed`, regardless of plan read permission | `satisfied` |
| Known incomplete/cancelled item or status/column mismatch | `dependency_unmet` |
| Declared ID absent from a successfully read authoritative board | `dependency_status_unavailable`, reason `dependency_not_found` |
| Authoritative source cannot be established/read | `dependency_status_unavailable`, stable source-failure reason |
| No declared dependencies | Satisfied on the dependency dimension |

`content_access_denied` describes a separate content authorization result. It never changes a dependency outcome. An unavailable row may have unknown tier/status/column and no completion evidence; do not fabricate those fields from stale content.

### Planning and action boundaries

Inject the minimal projection into every epic and feature planning turn and provide a scope-bound read-only refresh through the existing planning tool registration/MCP transport. Derive the allowed IDs from the caller's current owning spec; this is not an arbitrary board lookup. Keep document guards and filesystem allowlists unchanged.

At sign-off, approval, and feature-mint authorization, reread the owning item's current dependency declarations and authoritative lifecycle state. A turn-start projection, prior transcript, unchanged plan SHA, or cached/request-scoped board snapshot cannot authorize the action. Perform the recheck within the existing action/lifecycle synchronization boundary, using a minimal revision-checked retry/refusal if needed to close a race. Refuse without authorization-dependent side effects on unmet or unavailable evidence. Approval/readiness and dispatch consume the same lifecycle result while retaining their existing non-dependency checks.

This boundary applies to the owning item's prerequisites. Minting a backlog child may declare unfinished but valid predecessor features; requiring those predecessors to finish before their successor can even be planned would prevent normal decomposition. Preserve existing declaration validation.

Epic-plan approval is owned by the epic: recheck the epic's prerequisites before recording its approval and the existing bulk approvals of its backlog children. Unfinished valid sibling predecessors do not block that bulk plan approval. Those child approval records are not proof of dependency satisfaction; each child's activation/dispatch still checks its own current prerequisites, and direct feature sign-off/approval checks the feature's prerequisites. Keep these action scopes explicit when sharing the evaluator.

### Current status and history

Readiness, minting guidance, War Room live status, and generated current summaries consume the structured projection. Keep stable codes separate from explanatory text. Refresh via existing board/readiness request paths. Preserve dated transcript messages verbatim, identify snapshot-based observations as historical, and distinguish a current structured summary from old agent prose. Never parse chat to determine live readiness or retroactively rewrite history.

### Implementation anchors and risks

Current code has duplicated completion checks in `cascade/watchdog/dispatch.py`, `cascade/boss/view.py`, `cascade/feature/readiness.py`, and `cascade/stacked_dispatch.py`. `cascade/workspace/integration_worktree.py` owns merged-board precedence, a short-lived cache, and request-scoped snapshots; `cascade/board/context.py` resolves tracking ownership. Planning context/tools live under `cascade/agent/`; role sign-offs/readiness under `cascade/epic/`; minting under `cascade/epic/mint.py`; live serialization and transcript presentation under `cascade/war_room/`.

The first feature must characterize existing review/stacked behavior and tracking-root/merged-board precedence before extracting the evaluator. The second must prove fresh reads bypass stale cache/request snapshots and cover the action's commit point. The third must prove live status updates without rewriting historical messages. These are implementation acceptance obligations, not separate discovery features.

## Cross-module constraints

Reuse the canonical merged-board and lifecycle predicates rather than introducing a second dependency database or parsing chat prose. Preserve fail-closed behavior when authoritative status truly cannot be established. Do not broaden scoped document access. Keep stable machine-readable blocker codes separate from human explanations.

Retain existing review, approval, role-specific sign-off, and stacked-dispatch semantics; distinguish lifecycle satisfaction from any remaining action blocker. All consumers must agree for the same authoritative snapshot. Normal refresh may observe newer state; timestamps/fingerprints must make that distinction clear.

Out of scope: a new dependency graph validator, dependency authoring UI, automatic downstream activation, permission expansion, transcript migration, dashboard redesign, new polling infrastructure, or a general approval/scheduling rewrite.

## Core dependencies

- No new inter-epic prerequisite is declared; epic metadata remains `depends_on: []`.
- Reuse existing tracking-root resolution, merged-board precedence/invalidation, lifecycle/review predicates, planning tool transport, readiness/sign-off/approval/minting paths, and War Room read models.
- The epic_034/epic_036 sequence is a synthetic regression scenario, not a dependency on reading either team's production spec.

## Feature breakdown

| Feature | Deliverable | Depends on | Epic criteria |
| --- | --- | --- | --- |
| feat_038_001 — Expose authoritative dependency status to planning | Shared evaluator, minimal projection, planning context and scoped refresh; unchanged content authorization | None | 1, 2, 3, 4; foundational cases for 7 |
| feat_038_002 — Recheck dependency status at planning action boundaries | Fresh action-boundary checks, readiness and dispatch consistency, safe mid-turn changes | feat_038_001 | 2, 4, 5, 6, 7 |
| feat_038_003 — Align dependency reporting and lock end-to-end regressions | Current/historical reporting, War Room consistency, synthetic incident regression and acceptance evidence | feat_038_002 | 4, 5, 7, 8 |

Deliver in that order. Each feature includes its own relevant tests; the final feature closes cross-surface acceptance rather than deferring all verification until the end.

## Validation and acceptance

Extend the existing board/tracking, planning sandbox/tools, sign-off/readiness, minting, dispatch/lifecycle, and War Room suites. Prefer integrated scenarios over redundant helper tests. Cover completed/unreadable, readable/incomplete, absent ID, source failure, tracking-repository ownership, stale active worktree versus canonical completion, no dependencies, and review/stacked compatibility.

Drive both incomplete-to-completed and satisfied-to-unmet/unavailable transitions between context creation and the action. Preload a board cache/request snapshot and assert the mutation boundary uses fresh evidence; refused actions leave no new sign-off, approval, or child artifact. Assert that sequential backlog children can still be minted and bulk-approved with their epic while predecessors are unfinished; approved successors remain undispatchable until their own prerequisites are satisfied. An unmet/unavailable epic prerequisite must refuse bulk approval before any child approval is written.

Use a synthetic epic_034 -> epic_036 fixture: epic_036's canonical completion supersedes its stale active copy; epic_034 still cannot read epic_036's body; live planning/readiness recognizes completion without restarting the dependent epic. Verify historical blockers remain history. Feature 3 provides a success-criteria-to-test mapping and results of the affected suites. No live production spec access or broad coverage target is required.

## Open questions

No unresolved product-scope question remains. The initial implementation-risk question is addressed by the compatibility, freshness, authorization, and history obligations above. Exact evaluator/module naming and synchronization mechanics belong to feature design and must satisfy this contract.

## Decision log

- 2026-11-06 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-06 · Epic Manager · **Macro-architecture**
  Chose Use one minimal dependency projection from canonical merged-board/lifecycle state, with satisfied, dependency_unmet, and dependency_status_unavailable outcomes; keep content_access_denied independent..
  Rationale: A scoped plan-body denial provides no completion evidence. Absent IDs and unavailable authoritative sources remain distinguishable, fail-closed cases without expanding cross-team content access.
  Honors: Success criteria 1–4; canonical tracking ownership and existing review/stacked-dispatch rules..

- `dec_002` · 2026-11-06 · Epic Manager · **Macro-architecture**
  Chose Recheck the owning item's dependencies at sign-off, approval, and minting authorization; permit backlog children to declare unfinished valid predecessor features..
  Rationale: Fresh boundary evidence prevents stale authorization while allowing ordinary feature decomposition. Cached/request snapshots and unchanged plan revisions cannot substitute for current lifecycle evidence.
  Honors: Success criteria 5–7; preserve existing declaration validation, role sign-offs, and non-dependency action checks..

- `dec_003` · 2026-11-06 · Epic Manager · **Feature breakdown**
  Chose Deliver feat_038_001, then feat_038_002, then feat_038_003, with tests in each slice and final cross-surface regression evidence; preserve historical transcript text..
  Rationale: Three bounded features cover the full brief without adding a new status database, graph-validation project, UI redesign, or history migration. The synthetic epic_034/epic_036 fixture validates the incident without accessing production plan content.
  Honors: All eight success criteria; frugal engineering and product-manager scope priorities..

- `dec_004` · 2026-11-06 · Epic Architect · **Macro-architecture**
  Chose Scope bulk epic-plan approval checks to the epic's prerequisites; preserve approval of sequenced backlog children while enforcing each child's prerequisites at activation/dispatch and direct feature sign-off/approval..
  Rationale: cascade/approvals.py already bulk-approves every child in approve_epic_plan. Applying each successor's completion gate to that operation would prevent approval of an ordinary sequential plan. Explicit ownership preserves existing approval behavior without allowing approval records to bypass fresh execution checks.
  Honors: Success criteria 5–7; existing approval semantics, sequential feature decomposition, and fail-closed action boundaries. Added matching epic and feat_038_002 regression obligations..

- `dec_005` · 2026-11-06 · Epic Manager · **Feature breakdown**
  Chose For feat_038_001 planning, retain the approved first slice: shared authoritative evaluator, minimal allowlisted projection, planning-context injection, and owning-spec-scoped read-only refresh. Characterize tracking-root/merged-board precedence and review/stacked compatibility before extraction. Document the projection contract and relevant integrated-test evidence in the feature artifacts for feat_038_002 and feat_038_003..
  Rationale: This handoff applies the approved epic contract without expanding scope. Feature 1 establishes reusable status evidence; feature 2 owns fresh authorization-boundary enforcement, including the bulk-approval distinction in dec_004; feature 3 owns current-versus-historical reporting and final cross-surface acceptance. Each slice includes its own tests. Any required change to the epic contract must return through the amendment protocol before adoption.
  Honors: Epic success criteria 1–8; dec_001–dec_004; unchanged document authorization; separate lifecycle satisfaction and action eligibility; existing exclusions and feature order. Snapshot timestamps/fingerprints remain evidence rather than authorization tokens..

- `dec_006` · 2026-11-06 · Epic Manager · **Feature breakdown**
  Chose For feat_038_002 planning, reuse Feature 1's authoritative evaluator and keep this slice focused on fresh owning-item dependency checks at sign-off, approval, and feature-mint authorization, plus readiness/dispatch consistency. Reread current dependency declarations and canonical state through the action commit point; cached/request snapshots, prior projections, and unchanged plan SHAs cannot authorize an action. Preserve dec_004: epic bulk approval checks epic prerequisites, permits unfinished valid sibling predecessors, and never substitutes for each child's current activation/dispatch or direct sign-off/approval checks..
  Rationale: This applies the approved contract without adding scope. Require integrated evidence for incomplete-to-completed and satisfied-to-unmet/unavailable changes, preloaded stale caches/request snapshots, and refusal without new sign-off, approval, or child artifacts. Cover an unmet/unavailable epic prerequisite refusing bulk approval before child approvals, and successful sequential mint/bulk approval with successors still gated at dispatch. Record the action-scope mapping, freshness/commit-point approach, stable outcomes, and affected test results in feature artifacts for Feature 3's reporting and final acceptance handoff. Route any necessary epic-contract change through the amendment protocol before adoption.
  Honors: Success criteria 2, 4, 5, 6, and 7; dec_001–dec_005; delivery order feat_038_001 → feat_038_002 → feat_038_003; existing role, review, merge, declaration-validation, and stacked-dispatch checks. Keep content authorization unchanged and content_access_denied independent of dependency status. Current/historical presentation and final cross-surface acceptance remain Feature 3; no new approval framework, polling infrastructure, or automatic activation..

- `dec_007` · 2026-11-06 · Epic Manager · **Feature breakdown**
  Chose For feat_038_003 planning, reuse the authoritative projection and fresh action checks delivered by the preceding slices. Align readiness, minting guidance, War Room live status, and generated current planning summaries on structured dependency outcomes for the same snapshot. Keep content_access_denied separate from dependency_unmet and dependency_status_unavailable; keep remaining action-eligibility blockers separate from lifecycle satisfaction. Preserve dated transcript messages verbatim and clearly distinguish historical observations from current status. Use existing refresh paths and observation timestamps/fingerprints..
  Rationale: Close the approved cross-surface acceptance obligations without duplicating earlier implementation or tests. Require the synthetic epic_034 -> epic_036 regression: canonical completion overrides a stale active copy, the dependent epic recognizes completion while active without restart, spec access remains denied, and historical blockers remain history. In feature artifacts, map all eight epic success criteria to concrete tests and affected-suite results, reusing Feature 1/2 evidence and adding only missing integrated coverage. Include completed/unreadable, readable/incomplete, missing/source-unavailable, tracking ownership, and current-status transitions; retain evidence for fresh boundary refusals without side effects and sequential bulk approval with dispatch gating. Identify any unmet criterion explicitly rather than claiming acceptance from completion metadata. Route any necessary epic-contract change through the amendment protocol before adoption.
  Honors: Success criteria 1–8; dec_001–dec_006; existing feature order and unchanged content authorization. No new status database, chat-derived readiness, historical-message migration, dashboard redesign, polling infrastructure, automatic downstream activation, or approval-framework rewrite. Existing role, review, merge, declaration-validation, and stacked-dispatch checks remain intact; snapshot evidence and child approval records do not authorize execution..

- `dec_008` · 2026-11-06 · Epic Manager · **Branch action recovery**
  Chose For recovery:epic_038:integration_branch_update, preserve the current active epic contract and dec_001–dec_007, and reconcile the stale backlog copy with lifecycle/approval evidence before retrying integration_branch_update. Do not restore the old backlog brief over the active plan or discard its approval evidence. Confirm the intended target ref trunk through the recovery workflow; do not silently substitute main..
  Rationale: BranchActionRecoveryRequested reports branch_conflict on docs/epics/1_backlog/epic_038_make_planning_dependency_status_authoritative.md. read_doc returns the active spec at revision cb4c80abeb2687ea87ea1afb3fce5d5b68736dad with plan_approved_at=None, while prior events report plan approval. Read-only Git inspection shows commit a6285a84379cb35356dace876f1386ded2e80a94 deleted the stale backlog copy and commit 7add80b7fd7a558c573f3c67ec7d25d16eff2356 added plan_approved_at '2026-11-06T19:52:48.306339+00:00' to that backlog path. This suggests a modify/delete lifecycle-copy conflict, but the exact failed merge sides are unverified: trunk is not locally resolvable and the epic worktree has no unmerged index entries. Available Cascade tools have no branch-recovery/retry operation and the filesystem is read-only, so this decision records a recovery handoff, not a completed merge or metadata repair.
  Honors: Keep the approved scope, feature sequence, bulk-approval semantics, content authorization, and decision history intact. The recovery owner must inspect the actual source/target/base, preserve legitimate approval and lifecycle evidence in one canonical epic record using supported operations, then retry the original action and verify its result. Board metadata reports all three features completed; it does not establish acceptance-test evidence or successful integration. No new feature, dependency blocker, acceptance claim, or epic-completion transition is introduced..

- `dec_009` · 2026-11-07 · Epic Manager · **Branch action recovery**
  Chose Resolve recovery:epic_038:integration_branch_update on epic/epic_038 by merging product trunk main at 7e8608a587d24bfda681b9c91efb5c79fd59356f, retaining the current completed Epic brief, all merged feat_038 work, and both dependency-status and branch-recovery tool registrations. Resolution committed as 1614ec52cf3a954f1fc193ef892607820ef1d2c3. Remove the obsolete backlog copy rather than restore it over the current plan..
  Rationale: The actual merge reproduced the recorded backlog modify/delete conflict plus four additive code conflicts with updated main. Cascade's _recovery_target_ref records the logical target trunk; _resolve_base_branch uses resolve_product_trunk, which resolves it to main here. Preserve approval evidence: the removed backlog copy at main/7add80b7 records plan_approved_at 2026-11-06T19:52:48.306339+00:00; existing sign-off history includes both roles on revision 8a611a4fde3d0ac9ee1c8b97e253579193371386 and is unchanged. The MCP write_doc adapter reloads canonical metadata and ignored the attempted timestamp transfer, so the timestamp is recorded here and in merge-parent history, not claimed as repaired frontmatter. The current Epic was already completed before this recovery; no lifecycle transition was made. Updated three regression assertions to inspect the scoped materialized context instead of the now-authorized owned-worktree cwd, retaining prompt privacy and document-denial assertions. Targeted dependency, planning, War Room, branch synchronization, and worktree permission suites: 75 passed in 38.27s. Both tool registrations and schemas checked; git diff checks passed.
  Honors: dec_008; unchanged approved scope, decision history, feature sequence, current Epic body and sign-offs; all three feature specs, fifteen task specs, and two evidence artifacts preserved byte-for-byte at the resolution commit. All edits and Git merges confined to the owned Epic worktree; no product-trunk or other-team-worktree modification and no dependency installation. Retry the original durable action through retry_integration_branch_update; successful incident completion must be verified from its result..

- `dec_010` · 2026-11-07 · Epic Manager · **Branch action recovery**
  Chose Keep the current completed Epic lifecycle unchanged after retry attempt 1 of epic_038:integration_branch_update refused with not_active. Preserve merge resolution 1614ec52cf3a954f1fc193ef892607820ef1d2c3 and do not claim that the original incident completed..
  Rationale: The authorized retry_integration_branch_update call returned recovery_state awaiting_owner_decision, attempt_count 1, and failure_classification owner_decision. The durable attempt records completion_metadata reason not_active and conflict_paths []; the recovery wrapper calls the active-only branch synchronization preflight before recognizing a no-op. The Epic was already completed at ee3b9079711d44e4fb2ec3ae775135a8b293f1f3 before this turn. The merge conflict has been resolved and tested, but repeating the same retry cannot overcome this lifecycle guard.
  Honors: No fabricated action success, manual recovery-state patch, or unapproved Epic reopening. The remaining explicit lifecycle choice is to support reconciliation of the stale integration-update action while retaining the completed Epic, or authorize reopening the Epic for the active-only update workflow. Product trunk and other teams' worktrees remain outside this repair's write scope..
## Amendment log

_(none)_
