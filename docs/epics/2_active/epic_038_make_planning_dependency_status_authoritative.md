---
id: epic_038
title: Make planning dependency status authoritative
tier: epic
status: active
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
updated: '2026-11-06'
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
## Amendment log

_(none)_
