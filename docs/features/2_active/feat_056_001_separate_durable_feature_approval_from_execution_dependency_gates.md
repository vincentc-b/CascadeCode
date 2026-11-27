---
id: feat_056_001
title: Separate durable Feature approval from execution dependency gates
tier: feature
status: active
parent: epic_056
children:
- task_056_001_001
- task_056_001_002
- task_056_001_003
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 4a1feb1e4e9b54d4bf545fa3687a216db2180de1
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
  swe: medium
approved_at: '2026-11-27T16:40:56.431058+00:00'
---
# Separate durable Feature approval from execution dependency gates

## Parent Epic

epic_056

## Scope

# Separate durable Feature approval from execution dependency gates

## Scope
Implement the approval boundary described by epic_056. A human may approve the current reviewed Feature scope while a known, structurally valid ordinary predecessor is incomplete. Approval never claims readiness or starts work before canonical execution gates pass.

Own cascade/approvals.py, planning_action_dependencies.py, dependency_evaluation.py only as needed, feature/readiness.py and readiness_evidence.py, and the approval HTTP response/projection contract. Preserve shared strict dependency checks for minting, Epic sign-off, dispatch and other planning actions. Reuse existing approval evidence, Watchdog/Boss dispatch and lifecycle review gates.

## Acceptance criteria
1. Trace every authorization gate before changing the individual Feature approval path. Keep current human identity, reviewed revision/context, corrective-plan, provider, architecture/comment and applicable software-manifest gates. Allow only known noncancelled predecessor incompleteness at this boundary. Missing dependency/source, cancellation and illegal status/column evidence refuse explicitly without mutating approval.
2. Define approval eligibility separately from dispatch readiness on the server. Preserve legacy response/projection fields; expose typed approval result, explanation, affected work IDs and canonical approval state. A successful saved approval followed by dispatch refusal remains a successful approval with waiting evidence.
3. Persist approval through existing document timestamp and feature_approvals.json evidence. Retain scope versus exact approval modes; review-context races and changed scope invalidate approval. Review dependency-declaration changes as part of this fence. A crash between document/evidence writes must remain non-dispatchable and recover through the existing approval path.
4. Refresh authoritative owner/dependency evidence under existing concurrency fences. Repeated/concurrent approval calls and later Watchdog/Boss ticks admit one Feature execution; approved work waits in backlog. No planning or Tasks run while dependencies, sibling activity, required integration, review, provider or software gates block.
5. Keep Epic bulk approval and late-child behavior consistent with the explicit contract: existing included children stay approved, newly minted children remain unapproved until explicit human approval, and repeated approval cannot accept stale reviewed scope.
6. Extend production API plus isolated real-Git tests from tests/test_planning_action_dependencies.py, test_approvals.py, test_approval_dispatch_integration.py and tests/war_room/test_late_mint_feature_approval_e2e.py. Cover incomplete/unknown/cancelled/regressed dependencies, software safety, architecture/provider refusal, stale review and scope, restart, duplicate/concurrent calls and unrelated blockers. Prove predecessor completion alone does not bypass required delivery evidence.
7. Update owning design requirements and diagrams with actual implementation. Feature team must put this acceptance criterion into its Tasks: reconcile cascade/DESIGN.md approval authority, cascade/feature/DESIGN.md evidence lifecycle, affected Watchdog interfaces, root links, and source-backed integrated Code coverage for approval/evaluation/evidence/dispatch. Preserve model-contract semantic IDs and pinned review workflow; validate source symbols, local rendering, Context→Containers→Components→Code, Level up, deep-link restore and pinned source opening. Record normal and failure/restart traces and any unchanged-view rationale.

## Dependencies
None. Software prerequisites are inherited from the owning Epic manifest.

## Non-goals
No new scheduler, approval ledger, automatic human approval, installation, deployment, blanket relaxation of require_action_dependencies, or change to supported stacked dispatch semantics.

## Data structures

The canonical `DependencyEvaluation` retains ordered per-predecessor `DependencyStatus` rows. Approval eligibility derives from that fresh evaluation and distinguishes a known, legal `dependency_incomplete` wait from missing source, missing work, cancellation, or status/column mismatch. No approval-only lifecycle store is introduced. The existing Feature document `approved_at` and tracking-root `feature_approvals.json` remain the two durable approval facts.

The approval receipt revision includes the sorted declared `depends_on` IDs in both ordinary scope and exact modes. It does not include mutable predecessor completion state: an approved Feature may wait and later become dispatchable without another human approval, while a changed declaration requires review again.

## API contracts

The individual `approve_feature(feature_id, root, inventory?, review_context?)` boundary accepts a fresh, structurally valid incomplete predecessor only for approval. It retains corrective-plan, selected-provider, lifecycle review, software, current review-context, and owning-document checks. `approve_epic_plan` and `require_action_dependencies` retain strict satisfied-only behavior.

The POST `/api/approve_feature` response preserves `ok`, `feature_id`, `newly_approved`, `dispatch_pending`, `dispatch_outcome`, and existing refusal codes. Add a typed approval outcome and canonical approval state, with explanatory reason and affected IDs. A committed approval remains an HTTP success when dispatch waits; a refusal precedes any approval write. The board readiness projection reports approval eligibility separately from execution blockers, preserving existing fields and their meanings. Exact field names are fixed by the implementation task and verified through HTTP tests.

## Logic flow

```mermaid
sequenceDiagram
    participant Human
    participant Approval
    participant Board
    participant Receipt
    participant Dispatch
    Human->>Approval: Approve reviewed Feature
    Approval->>Board: Lock and refresh owner, declaration, predecessors
    alt unknown, cancelled, illegal or other authorization refusal
        Approval-->>Human: Typed refusal; no write
    else known incomplete or satisfied predecessors, other gates pass
        Approval->>Board: Commit approved_at
        Approval->>Receipt: Commit revision-bound evidence
        Approval-->>Human: Saved approval and current wait reason
        Approval->>Dispatch: Existing reconciliation
        Dispatch->>Board: Recheck dependency, sibling and delivery gates
        Dispatch-->>Human: Started or waiting
    end
    Note over Board,Receipt: Crash between writes leaves unknown approval until explicit retry
```

## Task breakdown

1. `task_056_001_001` — Safe approval eligibility and durable revision fence. Depends on none. Owns individual approval policy, receipt digest, and focused dependency/receipt tests.
2. `task_056_001_002` — Typed approval API and board projection. Depends on `task_056_001_001`. Owns response serialization, approval eligibility presentation, and HTTP tests.
3. `task_056_001_003` — Dispatch integration and architecture reconciliation. Depends on `task_056_001_001` and `task_056_001_002`. Owns real-Git, restart and concurrency evidence plus final design/model validation.

## Diagram-impact inventory

| Level / view | Owning design and implementation | Planned reconciliation |
|---|---|---|
| Landscape `cascade-landscape`, context `cascade-context` | Root `DESIGN.md`; operator, Cascade and forge/provider systems | Verify no new person, system or external responsibility. Update root links only if the contract navigation changes. |
| Containers `cascade-containers` | Root and `cascade/DESIGN.md`; War Room, supervisor and repository artifacts | Verify the existing HTTP → supervisor → repository path still expresses approval and receipt persistence. No new container or store is planned. |
| Components `cascade-supervisor-components`, `cascade-team-components`, `cascade-war-room-components` | `cascade/DESIGN.md`, `cascade/feature/DESIGN.md`, `cascade/war_room/DESIGN.md`; approval, Feature evidence, Watchdog and dashboard boundaries | Reconcile responsibility text and links against actual code, including dispatch still owning admission. |
| Code `cascade-approval-code`, `cascade-feature-code`, `cascade-dashboard-code`, `cascade-war-room-http-code` | `approve_feature`, `evaluate_action_dependencies` and the approval-only evaluator, `_revision`, `approval_evidence`, `compute_feature_readiness`, HTTP handler and serializer | Add or adjust native custom Code nodes and source-contract semantic IDs for significant new symbols; verify source path, declaration kind and symbol. |
| Code `cascade-watchdog-code`, `cascade-boss-code` | `dispatch_feature`, `_dependency_review_pending`, `feature_dispatch_blockers`, `_deps_met` | Check that existing views remain accurate; update only if implementation changes these collaborators. |
| Behavior | Approval sequence in `cascade/DESIGN.md`, receipt state in `cascade/feature/DESIGN.md`, dispatch flow in `cascade/watchdog/DESIGN.md` | Trace one normal incomplete-predecessor approval and later dispatch, plus refused/cancelled evidence and crash/restart recovery. |

## Risks & upward questions

The scope receipt currently omits `depends_on`; task 1 must fence declaration changes without binding mutable predecessor state. Existing request identity behavior is preserved; the HTTP test must verify the actual route's current authentication boundary. No Epic contract change is needed.

## Decision log

- `dec_001` · 2026-11-27 · Feature Lead · **API contracts**
  Chose Use an approval-only eligibility check that accepts only a fresh dependency_incomplete row with legal status and column; keep require_action_dependencies strict for all other actions..
  Rationale: Approval records human acceptance of reviewed scope, while execution still requires complete lifecycle and delivery evidence. An explicit allowlist fails closed on missing, cancelled, malformed, or unavailable predecessors.
  Honors: epic_056 approval boundary; REQ-CASCADE-APPROVAL-001; REQ-WATCHDOG-DISPATCH-001.

- `dec_002` · 2026-11-27 · Feature Lead · **Data structures**
  Chose Bind sorted declared depends_on IDs into ordinary scope and exact approval receipt revisions, without binding mutable predecessor state..
  Rationale: Changing a dependency declaration changes approved scope, while a predecessor completing later must not force another approval. The existing document timestamp and JSON receipt remain the durable evidence pair.
  Honors: epic_056 durable approval contract; REQ-FEATURE-APPROVAL-001.

## Closeout

Completed child work: `task_056_001_001` (Define safe Feature approval eligibility and revision fence), `task_056_001_002` (Expose typed approval and waiting state in API and board), `task_056_001_003` (Verify execution gates and reconcile architecture).
