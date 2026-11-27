---
id: epic_056
title: Separate Feature approval from dispatch readiness and expose refusal reasons
tier: epic
status: active
parent: null
children:
- feat_056_001
- feat_056_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-27'
updated: '2026-11-27'
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
# Separate Feature approval from dispatch readiness and expose refusal reasons

## Intent

An operator attempting to approve feat_051_006 while its prerequisite feat_051_005 was still running received HTTP 409 dependency_unmet; the card reverted to Needs approval with no persistent actionable explanation. Epic 020 originally promised a durable approval independent of dependency, sibling, review and merge dispatch blockers. Restore the explicit distinction so a human can authorize reviewed future work without starting it prematurely, and so rejected or ambiguous actions are always visible. Coordinate with Epic 045 readiness explanations and Epic 039 dependency gates; no duplicate approval or execution authority.

### Success criteria

1. Distinguish human plan approval from dispatch readiness: permit explicit durable approval of the current reviewed Feature plan while an ordinary declared predecessor is incomplete, while preserving all independently required human review, dependency-manifest/software installation, provider selection and architecture approval gates. If a prerequisite is genuinely required to authorize approval rather than dispatch, refuse explicitly with the exact reason; never silently record acceptance of an unreviewed plan.
2. Keep approved work in backlog with its exact dependency, sibling, integration or review blockers. Re-evaluate only through the existing Watchdog/Boss dispatch path; never start planning or Tasks before their canonical prerequisites are met. When predecessors complete, dispatch exactly once without a second approval click. Preserve revision-bound approval evidence, idempotence, changed-plan invalidation and concurrency fences.
3. Align the board and plan-page controls with the authoritative approval boundary. Show immediate pending state, retain disabled state across polls, and distinguish approved-awaiting-prerequisite, explicit refusal and unconfirmed transport outcome. Display typed refusal explanations and blocker work IDs on the affected row, not merely in chat status, without reloading.
4. Reproduce feat_051_006 depending on active feat_051_005: approve once, verify persisted evidence across refresh/restart, prove no premature dispatch, then complete and verify the predecessor and observe exactly one dispatch. Cover late-minted approved/unapproved children, incomplete/unknown/cancelled dependencies, stale reviewed revisions, provider and architecture refusals, repeated clicks/polls, transport failure and unrelated blockers. Use production API and isolated real Git plus browser tests; retain existing approval and recovery gates.

## Macro-architecture

This is a proposal for review; implementation remains with the child Features after human plan approval.

### Authority and state

| Boundary | Owner and sources | Proposed contract |
|---|---|---|
| Human approval | `cascade/approvals.py:approve_feature`, `approve_epic_plan`; `planning_action_dependencies.py:evaluate_action_dependencies`; `lifecycle_review_gate.py:require_lifecycle_review_gate` | Refresh canonical owner/evidence under the existing lock; distinguish ordinary sequencing from authorization safety before any write. Accept an explicitly reviewed Feature while a known valid noncancelled predecessor is incomplete. |
| Authorization safety | Current human request verification, provider selection preflight, corrective-plan checks, architecture/review context, comment gates and applicable Epic software readiness | Preserve each independently required gate. Missing owner/source/dependency, cancellation and status-column mismatch are explicit refusals. A dispatch wait never waives an authorization gate. |
| Approval persistence | `approvals.py:_set_feature_approved`; `feature/readiness_evidence.py:write_approval_evidence`, `approval_evidence` | Reuse the owning document's approved_at and existing feature_approvals.json receipt. Preserve ordinary scope approval versus corrective exact approval and changed-plan invalidation. Unknown/partial evidence cannot dispatch. |
| Execution | `feature/readiness.py:evaluate_feature_readiness`; `watchdog/dispatch.py:dispatch_feature`, `dispatch_task`; `automation.py:reconcile_approval_dispatch`; `stacked_dispatch.py:feature_dispatch_blockers` | Approval can trigger the existing reconciliation path, but all dependency, sibling, delivery/integration, provider, review, capacity and lifecycle gates still apply. The canonical reservation/dispatch path admits one execution. |
| Operator projection | `war_room/server.py:WarRoomHandler._handle_approve_feature`; `war_room/static/war_room.js:featureApproveActionButton`, lifecycle action tracking; plan viewer/readiness controls | Server owns eligibility and typed outcomes. Browser tracks an in-flight action and renders canonical approval/readiness, explicit refusal and unknown transport outcome without conflating them. |

Before changing a source symbol named above, verify its exact declaration and owning component. API changes are additive: retain existing ok, feature_id, newly_approved and readiness consumers while exposing a consistent machine code, human explanation, affected work IDs and canonical approval state. Successful approval with deferred dispatch is not an HTTP approval failure. Do not turn polling into provider discovery, a state mutation or a second scheduler.

### Normal, failure and resume flows

1. The human reviews the current Feature scope and architecture tuple, then approves it. The server refreshes the owner and dependency facts, applies authorization safety and rejects stale reviewed evidence before persistence.
2. A known incomplete ordinary predecessor permits durable approval. The Feature remains in backlog with precise dispatch blockers. A response may report saved approval plus waiting evidence; no Feature planning or Task starts early.
3. Existing Watchdog/Boss reconciliation observes predecessor completion and the required delivery evidence. Other blockers continue to apply. Once eligible, the normal lock/reservation transition dispatches exactly once, without another human approval.
4. Repeated clicks or concurrent requests are idempotent against current approval evidence. A plan change invalidates the reviewed scope; dependency-declaration changes must be included in the fence assessment.
5. On server restart, read the document and existing approval receipt. A document write without matching receipt remains unknown/non-dispatchable and recovers through the canonical approval path. A disconnected browser reports an unconfirmed outcome and reconciles canonical state; it does not infer rejection or success from transport alone.

### Diagram-impact inventory and ownership

The authoritative model is `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{workspace.dsl,model.dsl,views.dsl,workspace.contract.json}`. Epic Architect owns the proposal and component assignment before sign-off. Child architects must transfer these rows into Task acceptance criteria; implementers reconcile them against the final diff.

| Level / view keys | Owning design and sources | Required work / owner | Verification |
|---|---|---|---|
| Landscape/context: cascade-landscape, cascade-context | DESIGN.md; existing operator, Cascade, provider and forge boundaries | Review only unless the diff changes external authority. No new actor or service is proposed. Epic Architect establishes rationale; both Features confirm it. | Compare model to final API authority and dependency inventory; source/design links resolve. |
| Containers: cascade-containers | DESIGN.md, cascade/DESIGN.md; local War Room, service and repository artifacts | Keep runtime topology; clarify approval persistence and request flow if labels imply immediate execution. feat_056_001. | Trace HTTP→approval receipt→Watchdog across existing boundaries; no invented OS isolation. |
| Components: cascade-supervisor-components, cascade-team-components | cascade/DESIGN.md, cascade/feature/DESIGN.md, cascade/watchdog/DESIGN.md | Assign approval/evaluation/evidence ownership and distinguish it from dispatch. feat_056_001. | Normal wait/release and unknown/stale/refusal traces against actual source. |
| Components: cascade-war-room-components | cascade/war_room/DESIGN.md | Clarify HTTP approval versus dashboard projection and client pending state. feat_056_002. | API and UI agree on refusal, pending, approved waiting and confirmed state. |
| Integrated Code: cascade-feature-code, cascade-watchdog-code, cascade-boss-code; focused approval view if current component mapping requires one | cascade/DESIGN.md owns approval service; cascade/feature/DESIGN.md owns evidence; Watchdog owns dispatch; symbols in authority table | Existing team view does not by itself explain approval/evidence. Architect selects correct component ownership and native custom view; feat_056_001 adds source-linked approval, dependency-policy and persistence nodes/relationships and reconciles dispatch links. | Each view has cascade.codeComponent; nodes have cascade.parent, sourcePath, sourceSymbol and correct native declaration kind. Synchronize contract; validate changed/removed symbols and ownership. |
| Integrated Code: cascade-war-room-http-code, cascade-dashboard-code | cascade/war_room/DESIGN.md; server approval handler, featureApproveActionButton, lifecycle actions and plan controls | feat_056_002 updates concrete request/result/polling functions and their relationships. | Context→Containers→Components→Code, Level up, deep-link restore and pinned source opening in actual UI; bounded local render and warm artifact reuse measurements. |
| Supplementary behavior | cascade/DESIGN.md approval sequence; cascade/feature/DESIGN.md evidence recovery; cascade/war_room/DESIGN.md action-state flow | feat_056_001 owns authorization/persistence/resume diagram; feat_056_002 owns client pending/refusal/unconfirmed reconciliation. | One normal and one failure/restart scenario tied to API/Git/browser evidence. |

No accepted snapshot may be rewritten to satisfy verification. Render success alone is insufficient; record navigation, source links, warm reuse and limitations. Unchanged levels need the diff-specific rationale above confirmed at closeout.

## Cross-module constraints

- Keep strict shared work-dependency enforcement for Epic sign-off, minting, dispatch and other planning actions. Scope the new distinction to explicit Feature approval and its relevant projections; do not weaken require_action_dependencies globally.
- Preserve existing review/provider/software-installation authority. A known cancelled or invalid predecessor is not merely slow work; it requires a visible correction/disposition before new approval. Unknown evidence fails closed.
- Preserve Epic bulk approval's reviewed child set and late-minted unapproved children. Repeat approvals must not accept a revised or newly added scope without current human review.
- Keep existing stacked-dispatch and intended-target integration contracts. Lifecycle completion alone is not proof of delivered code.
- Reuse existing approval receipt and lifecycle action state. No additional durable approval ledger, automatic approval, scheduler, broad UI redesign, installation or deployment.
- Coordinate with the contracts delivered by Epics 020, 039, 045 and 051 through current source/design interfaces. No dependency on an unrelated delivery is invented; overlapping edits require reconciliation before merge.

## Core dependencies

Canonical dependency manifest revision 3 is ready: twelve exact existing prerequisites passed the bounded verification recipes. Python 3.12.8; PyYAML 6.0.3; cursor-sdk 1.0.37; langgraph 1.2.14; langgraph-checkpoint-sqlite 3.1.1; pytest 9.0.3; Playwright 1.64.0; Chromium 156.0.8078.4; Git 2.34.1; Node 20.20.2; Docker 28.0.0; Structurizr image pinned by sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c.

The declared target is the local check host ip-172-31-37-14 (Linux x86_64, /opt/conda/bin/python3.12, repository/check executor root /home/ubuntu/dev/CascadeCode). The owned implementation worktree is /home/ubuntu/dev/CascadeCode/.cascade/worktrees/epic_epic_056. This is a verification target, not an inferred deployment target. No install or upgrade is authorized; no provider/forge credentials or production incident mutation are required for isolated tests. The manifest contains version, source, integrity reference and recipe for every entry; package RECORD hashes establish the inspected installation baseline, not an upstream supply-chain attestation.

## Feature breakdown

| Feature | Deliverable | depends_on | Success criteria |
|---|---|---|---|
| feat_056_001 | Separate durable Feature approval from execution dependency gates; authoritative response/projection, persistence and API/Git regression coverage | [] | 1, 2 and backend portions of 4 |
| feat_056_002 | Show Feature approval outcomes and verify deferred dispatch end to end; board/plan controls and API-backed browser journey | [feat_056_001] | 3 and complete acceptance journey in 4 |

Both Feature records contain design and integrated Code-view obligations. The second consumes the first's contract. Keep testing inside these slices; no separate test-only Feature or speculative framework is needed.

## Validation and delivery evidence

Use existing production HTTP and isolated real-Git fixtures in tests/test_planning_action_dependencies.py, tests/test_approvals.py, tests/test_approval_dispatch_integration.py, tests/test_approval_selection_gate.py, tests/war_room/test_late_mint_feature_approval_e2e.py and readiness/browser suites. Update the specific old assertion that incomplete predecessors must refuse individual Feature approval; retain strict checks at other boundaries.

The mandatory journey models feat_051_006 waiting on active feat_051_005 without modifying those live work records. Observe persisted current approval across refresh/server restart, zero early Feature/Task starts, then completed and verified predecessor delivery followed by one canonical dispatch event/reservation. Cover late children, unknown/cancelled dependencies, stale reviews, provider/architecture/software refusals, duplicate requests/polls, transport ambiguity and unrelated blockers. Browser coverage must use the API; static source assertions are supplementary.

Closeout records exact test commands/results, dispatch evidence, reviewed design paths and diagram rows, source-contract validation, render/UI navigation and warm-reuse measurements. A skipped browser or render check is an explicit gap, not a pass.

## Open questions

No unresolved product-scope question. Before sign-off, Epic Architect must finalize approval-code component ownership, reconcile affected design prose/model proposal and confirm the authorization-gate matrix. The manager must review that final revision and then sign off only for epic_manager.

## Planning review and handoff

Manager inspected approvals.py, planning_action_dependencies.py, dependency_evaluation.py, lifecycle_review_gate.py, Feature readiness/evidence, approval HTTP handling, existing API/Git fixtures, root DESIGN.md and affected sections of cascade/DESIGN.md, cascade/feature/DESIGN.md, cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md, plus current C4 view keys.

Concrete documentation gap: root DESIGN.md describes durable approval in .cascade/approvals.json, while current code writes the owning document timestamp and Feature readiness approval evidence. Epic Architect should correct this current-state statement and add source-linked approval coverage before plan publication. Existing scope/exact approval modes and declaration-change invalidation also need explicit architectural review. No design completeness, render/navigation result or behavioral test result is claimed in this planning turn; only prerequisite checks ran. Sign-off is pending the architect's reconciliation and manager review of its final revision.

## Decision log

- 2026-11-27 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
