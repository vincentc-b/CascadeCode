---
id: epic_056
title: Separate Feature approval from dispatch readiness and expose refusal reasons
tier: epic
status: completed
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
| Execution | `feature/readiness.py:compute_feature_readiness`; `watchdog/dispatch.py:dispatch_feature`, `dispatch_task`; `automation.py:reconcile_approval_dispatch`; `stacked_dispatch.py:feature_dispatch_blockers` | Approval can trigger the existing reconciliation path, but all dependency, sibling, delivery/integration, provider, review, capacity and lifecycle gates still apply. The canonical reservation/dispatch path admits one execution. |
| Operator projection | `war_room/server.py:WarRoomRequestHandler._handle_approve_feature`; `war_room/static/war_room.js:featureApproveActionButton`, lifecycle action tracking; plan viewer/readiness controls | Server owns eligibility and typed outcomes. Browser tracks an in-flight action and renders canonical approval/readiness, explicit refusal and unknown transport outcome without conflating them. |

Before changing a source symbol named above, verify its exact declaration and owning component. API changes are additive: retain existing ok, feature_id, newly_approved and readiness consumers while exposing a consistent machine code, human explanation, affected work IDs and canonical approval state. Successful approval with deferred dispatch is not an HTTP approval failure. Do not turn polling into provider discovery, a state mutation or a second scheduler.

### Normal, failure and resume flows

1. The human reviews the current Feature scope and architecture tuple, then approves it. The server refreshes the owner and dependency facts, applies authorization safety and rejects stale reviewed evidence before persistence.
2. A known incomplete ordinary predecessor permits durable approval. The Feature remains in backlog with precise dispatch blockers. A response may report saved approval plus waiting evidence; no Feature planning or Task starts early.
3. Existing Watchdog/Boss reconciliation observes predecessor completion and the required delivery evidence. Other blockers continue to apply. Once eligible, the normal lock/reservation transition dispatches exactly once, without another human approval.
4. Repeated clicks or concurrent requests are idempotent against current approval evidence. A plan change invalidates the reviewed scope; dependency-declaration changes must be included in the fence assessment.
5. On server restart, read the document and existing approval receipt. A document write without matching receipt remains unknown/non-dispatchable and recovers through the canonical approval path. A disconnected browser reports an unconfirmed outcome and reconciles canonical state; it does not infer rejection or success from transport alone.

### Authorization-gate matrix

This matrix is normative for feat_056_001; the source observations describe the planning baseline, not a claim that the proposed behavior already exists.

| Gate / authoritative source | Individual Feature approval | Execution / other boundaries |
|---|---|---|
| Explicit human request — `war_room/human_auth.py`, HTTP approval route | Require the existing request-scoped human verification before writes; do not trust a body actor. Inspection found `_handle_approve_feature` does not currently call the verifier. Wire the existing authority into this route and test denied requests without adding another identity mechanism. | Keep existing dispatch actor, role and tool restrictions. Approval never authorizes provider work by itself. |
| Owning document / declaration — `evaluate_action_dependencies`, `dependency_evaluation.evaluate_dependencies` | Refresh canonical owner and all rows under the existing lock. Only `dependency_incomplete` for a known noncancelled dependency in its legal column is permissible. Any missing owner/source/ID, cancelled dependency or status-column mismatch refuses; inspect every row, not only the aggregate outcome. | Strict `require_action_dependencies` remains strict for minting, sign-off and other planning actions. Watchdog still requires all dependency lifecycle and delivery gates. |
| Reviewed revision — `ReviewApprovalContext`, `readiness_evidence._revision` | Submit the displayed scope/exact revision and dependency-declaration fingerprint with the architecture tuple. Revalidate the same owner and declaration immediately before timestamp and receipt writes. Stale or absent required reviewed context refuses before mutation, including repeated approval. | A current matching receipt is required; status movement alone is not new scope. |
| Corrective authorization — `require_corrective_feature_ready_for_approval` | Preserve accepted-work disposition, ready corrective plan and exact approval mode. | Preserve generation-bound repair and delivery checks. |
| Provider selection — `_require_approval_selections` | Preflight the Feature and relevant Tasks before the first write. Unsupported and unavailable remain distinct typed refusals. | Recheck at actual dispatch; GET polling does not discover providers. |
| Architecture/comments — `require_lifecycle_review_gate` | Preserve rollout-aware exact tuple, accepted-lineage and unresolved comment gates; expose their actual codes instead of generic conflict alone. | Recheck dispatch/recovery boundaries and scoped change holds. |
| Software prerequisites — `epic/dependency_evidence.compute_dependency_readiness`, `require_epic_plan_ready_for_approval` | Epic bulk approval already checks this authority. Individual approval must consult applicable owning-Epic software readiness directly, including stale/unknown evidence; do not rerun unrelated role sign-offs or treat ordinary work dependencies as installation authority. Reuse the dependency-installation approval authority; never install here. | Preserve bootstrap and setup authorization. If readiness regresses after approval, no execution may start until the applicable gate is current. Add the canonical gate at admission if tracing exposes a missing direct check. |
| Sibling activity, merge/review delivery, dispatch base, capacity — readiness / stacked dispatch / Watchdog | Dispatch waits do not refuse otherwise valid explicit approval. Approval-specific unresolved review comments in the preceding row still refuse. | All remain blocking until independently satisfied; completed predecessor metadata cannot substitute for intended-target delivery. |
| Duplicate request and partial persistence — `_feature_needs_approval`, `_set_feature_approved`, receipt owner | Only matching current evidence is idempotent success. Timestamp without matching receipt is unknown; do not report committed approval or dispatch merely from the timestamp. Recovery uses explicit current review and existing write path. | Existing lifecycle lock and execution reservation admit one execution. No second scheduler or ledger. |

### Declaration and request fencing decision

feat_056_001 must version the existing receipt and add a dependency-declaration fingerprint derived from sorted unique `depends_on` IDs. Compare it for both scope and exact modes, and include it in the displayed/requested authorization identity. Canonicalization permits ordering-only changes; adding, removing or replacing an ID invalidates approval. Do not include predecessor status, dispatch blockers, timestamps or delivery observation time: their normal progress must release work without another human click. Retain the existing scope-body exclusions for delegated tactical planning and exact mode for corrective work.

Keep the existing content revision separate if needed for bounded historical proof; merely changing `_revision` without compatibility treatment is insufficient. Existing receipts without declaration evidence remain unknown unless a bounded immutable approved-document reference proves both the approved content and the dependency declaration. The current digest alone cannot prove a declaration it never hashed. If proof is ambiguous, require explicit human reapproval; never backfill from today's document or silently trust an old receipt. Tests must cover same-body historical commits with different declarations, stale browser request versus current owner, declaration mutation between checks/writes, and crash/restart between timestamp and receipt. No automatic human authorization is introduced.

Epic bulk approval must bind its displayed child set and each child's approval identity. A late child stays unapproved until explicitly included in a newly reviewed request. A replay of an earlier request must not approve it. This qualifies the current implementation's repeated-approval behavior, which can include new children; it does not require a new approval authority.

### Final component assignment

The existing in-process orchestration is `element.component.approval`, owned by `cascade/DESIGN.md#feature-approval-authority` (`REQ-CASCADE-APPROVAL-001`, `DEC-CASCADE-APPROVAL-001`), with native custom `cascade-approval-code`. It contains `approve_feature`, `approve_epic_plan`, `evaluate_action_dependencies`, strict `require_action_dependencies`, `require_lifecycle_review_gate`, `_set_feature_approved` and `reconcile_approval_dispatch`. This is a code responsibility inside Service, not a deployment unit.

`element.component.feature-team` owns `write_approval_evidence`, `approval_evidence`, `_revision`, and `compute_feature_readiness` in `cascade-feature-code` and `cascade/feature/DESIGN.md#approval-evidence-and-readiness` (`REQ-FEATURE-APPROVAL-001`, `DEC-FEATURE-APPROVAL-001`). `element.component.watchdog` keeps canonical dispatch; Boss keeps ordering and integration. War Room HTTP owns `_handle_approve_feature`; dashboard owns `featureApproveActionButton` and existing lifecycle/plan controls. The model and contract now expose these current source symbols. The implementation teams must reconcile labels and relationships when the dependency policy and request/result contract change.

### Diagram-impact inventory and ownership

The authoritative model is `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{workspace.dsl,model.dsl,views.dsl,workspace.contract.json}`. Epic Architect owns the proposal and component assignment before sign-off. Child architects must transfer these rows into Task acceptance criteria; implementers reconcile them against the final diff.

| Level / view keys | Owning design and sources | Required work / owner | Verification |
|---|---|---|---|
| Landscape/context: cascade-landscape, cascade-context | DESIGN.md; existing operator, Cascade, provider and forge boundaries | Review only unless the diff changes external authority. No new actor or service is proposed. Epic Architect establishes rationale; both Features confirm it. | Compare model to final API authority and dependency inventory; source/design links resolve. |
| Containers: cascade-containers | DESIGN.md, cascade/DESIGN.md; local War Room, service and repository artifacts | Keep runtime topology; clarify approval persistence and request flow if labels imply immediate execution. feat_056_001. | Trace HTTP→approval receipt→Watchdog across existing boundaries; no invented OS isolation. |
| Components: cascade-supervisor-components, cascade-team-components | cascade/DESIGN.md, cascade/feature/DESIGN.md, cascade/watchdog/DESIGN.md | Assign approval/evaluation/evidence ownership and distinguish it from dispatch. feat_056_001. | Normal wait/release and unknown/stale/refusal traces against actual source. |
| Components: cascade-war-room-components | cascade/war_room/DESIGN.md | Clarify HTTP approval versus dashboard projection and client pending state. feat_056_002. | API and UI agree on refusal, pending, approved waiting and confirmed state. |
| Integrated Code: cascade-approval-code, cascade-feature-code, cascade-watchdog-code, cascade-boss-code | cascade/DESIGN.md owns approval service; cascade/feature/DESIGN.md owns evidence; Watchdog owns dispatch; symbols in authority table | Approval component and receipt/readiness nodes are established in the planning artifact. feat_056_001 reconciles their labels, declaration fence, dependency-policy relationships and dispatch links against implemented code. | Each view has cascade.codeComponent; nodes have cascade.parent, sourcePath, sourceSymbol and correct native declaration kind. Synchronize contract; validate changed/removed symbols and ownership. |
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

No unresolved product-scope or architecture-boundary question. The declaration fence, gate matrix and component ownership above resolve the manager handoff. The manager must review the final architect revision and sign off only for epic_manager. Human approval and child implementation remain separate subsequent actions.

## Planning review and handoff

Manager inspected approvals.py, planning_action_dependencies.py, dependency_evaluation.py, lifecycle_review_gate.py, Feature readiness/evidence, approval HTTP handling, existing API/Git fixtures, root DESIGN.md and affected sections of cascade/DESIGN.md, cascade/feature/DESIGN.md, cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md, plus current C4 view keys.

Concrete documentation gap: root DESIGN.md describes durable approval in .cascade/approvals.json, while current code writes the owning document timestamp and Feature readiness approval evidence. Epic Architect should correct this current-state statement and add source-linked approval coverage before plan publication. Existing scope/exact approval modes and declaration-change invalidation also need explicit architectural review. No design completeness, render/navigation result or behavioral test result is claimed in this planning turn; only prerequisite checks ran. Sign-off is pending the architect's reconciliation and manager review of its final revision.

### Manager follow-up review

Reviewed canonical plan revision baec539220c27ba6b337674140e4ca627deda35d against the clean owned checkout. The two existing Features cover the requested backend authority and UI journey; no additional Feature is needed. Source inspection confirms that individual approve_feature calls strict require_action_dependencies before authorization/persistence, while approval_evidence distinguishes scope and exact receipts. Its _revision hashes body, parent and provider/model configuration but omits frontmatter depends_on. A dependency declaration edit therefore needs an explicit approval-fence decision; the existing digest must not be assumed to bind it. Preserve ordinary tactical-plan evolution allowed by scope mode, and distinguish a declaration edit from a predecessor lifecycle transition, which must not demand another approval.

Reviewed relevant approval/readiness sections in DESIGN.md, cascade/DESIGN.md, cascade/feature/DESIGN.md, cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md, and existing model/views. The root approvals.json statement remains stale; the Feature Code view currently covers team execution and repair without approval/evidence entry points. These remain Epic Architect handoff items before sign-off, together with the authorization-gate matrix and exact component assignment. In particular, the HTTP handler returns dependency codes/reasons but no affected dependency IDs, and generic architecture/value errors use the generic conflict response; feat_056_001 owns consistent typed projection and feat_056_002 consumes it. No production code or design model was changed in this review. Verification was read-only source/design inspection and clean Git status, not a behavioral, rendering or navigation test. Those checks must accompany the architect's artifact reconciliation and child implementation as assigned in the inventory. Manager sign-off remains pending the final reconciled revision.

### Architect reconciliation and verification

The architect resolved the manager’s three handoff items: declaration fencing is specified above; the root storage statement now names owning-document timestamps and tracking-root feature_approvals.json; approval/evidence Code ownership and the gate matrix are explicit. Reviewed DESIGN.md, cascade/DESIGN.md, cascade/feature/DESIGN.md, cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md against approvals, dependency evaluation, lifecycle review, readiness/evidence, HTTP handling and dispatch sources. Root/package/Feature designs were corrected and expanded with current implementation links and normal/failure flows. Watchdog and War Room behavior is unchanged in this planning diff; their current dispatch and projection contracts remain valid. Their implementation changes and updated behavior diagrams belong to the respective child Features.

Planning model changes add a Service component and native Code view, receipt/readiness nodes and HTTP/dashboard entry points. They describe current source, including strict dependency refusal and the current digest omission; they do not claim the proposed policy is implemented. Landscape/context and containers need no edit because no actor, process, repository, provider or transport boundary changes. Supervisor/team component views include the approval responsibility; War Room component ownership is unchanged and its Code coverage is extended. Watchdog/Boss Code views retain their existing admission/delivery nodes because those implementations are unchanged; feat_056_001 must reconcile any admission-gate changes. No accepted snapshots, historical evidence or runtime Python/JavaScript were edited.

Initial checks: validate_c4_workspace accepted all 25 views; every modeled code symbol and native declaration kind resolved through the repository renderer test helper. The final check results and publication pins are recorded below before architect sign-off. Source trace: strict dependency checks currently refuse an incomplete predecessor before timestamp persistence; successful approval writes timestamp then receipt and calls existing reconciliation; an interrupted receipt write makes dispatch evidence unknown and reapproval is the recovery path. The proposed wait/release behavior is not yet implemented or behaviorally verified; child API/Git/browser acceptance remains mandatory.

### Manager review of reconciled proposal

Reviewed plan revision 7e3e12be19b4307e78f7e737bd55e92825726e04 and the six-file working-tree architecture/design diff. The declaration fingerprint and compatibility policy in dec_003, explicit authorization-gate matrix, and component assignment in dec_004 resolve the earlier manager scope/ownership questions. The existing two Features remain sufficient; no additional Feature or implementation authority is introduced.

Reviewed DESIGN.md, cascade/DESIGN.md and cascade/feature/DESIGN.md changes against approve_feature, approve_epic_plan, _feature_needs_approval, _set_feature_approved and readiness_evidence. Also reviewed the affected dispatch/readiness interfaces in cascade/watchdog/DESIGN.md and cascade/war_room/DESIGN.md. The root receipt-storage correction is accurate; the new sections distinguish current strict dependency enforcement and current digest limitations from the proposed behavior. Normal persistence/reconciliation and interrupted timestamp/receipt recovery agree with the inspected source. New requirement/decision ownership, source links and behavior diagrams are appropriate. No delivery attribution violation was found in the changed design prose or diagram labels.

Manager verification: /opt/conda/bin/python3.12 invoked validate_c4_workspace on architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5 successfully; the _declaration_kind helper from tests/workspace/test_c4_render.py resolved all 265 modeled source nodes with matching native kinds; relative file links in the three changed designs resolved; git diff --check passed. These were source-contract, declaration, link and diff checks, not a render, browser navigation test or behavioral approval test. The diagram-impact inventory assigns all changed levels and downstream Task acceptance obligations; unchanged context/container and Watchdog/Boss levels have concrete current-diff reasons.

Remaining architect handoff before final manager sign-off: finish the promised verification closeout and revision-pinned architecture publication for the reconciled source; record bounded render results, actual Context→Containers→Components→Code and Level up navigation, deep-link restoration, representative pinned-source opening, warm-artifact reuse measurements and any explicit limitations. The current plan still promises final results/pins below but contains none, and the supplied architecture context has no artifacts. Manager sign-off remains pending that final reviewable revision. Child API/Git/browser tests of the proposed approval policy remain implementation acceptance obligations, not planning passes.

### Final architect verification and publication pins

The reviewed design/model source is commit `9d0ba60ae79d1c3319aa6fa277202846fa225028`. It binds DESIGN.md, cascade/DESIGN.md, cascade/feature/DESIGN.md and all four authoritative files under architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/. [Architecture evidence](../../epic_artifacts/epic_056_architecture_evidence.json) was committed in `a19c9ecb`; the [browser harness](../../epic_artifacts/epic_056_architecture_browser.py) reproduces the navigation check. The publication payload at docs/epic_artifacts/epic_056_architecture_review.json binds this source commit to the final plan revision produced by this update. Accepted lineage epic:epic_056 has no current baseline: expected generation is null and the baseline is explicitly empty. Publication uses the normal Cascade revision-pinned workflow; no accepted snapshot was rewritten.

Verification performed:

- `/opt/conda/bin/python3.12 -m pytest -q tests/workspace/test_c4_source.py tests/workspace/test_c4_review.py tests/war_room/test_architecture_http.py`: **40 passed in 21.29s**, including confined source metadata, invalid component ownership and native Code scope checks.
- `validate_c4_workspace` accepted 292 elements and 25 views. The existing tests/workspace/test_c4_render.py:_declaration_kind helper resolved all 265 modeled declarations with matching native kinds against the rendered workspace. Temporary renamed/deleted approve_feature declarations were rejected by that helper. These are explicit source checks; the C4 parser alone does not verify declaration existence.
- All 186 relative file links in the three changed designs resolved. Reviewed those designs and affected Watchdog/War Room interfaces for single requirement ownership, current facts, execution, persistence/recovery and delivery attribution. `git diff --check` passed. No new meaningful code directory requires a child design.
- `PYTHONPATH=. /opt/conda/bin/python3.12 docs/epic_artifacts/epic_056_architecture_browser.py` passed with real architecture HTTP routes, Chromium and the pinned local Structurizr renderer. All 25 interactive views rendered in **58.57 seconds** with unchanged limits: 180 seconds, 2 CPUs, 1536m memory, 256 PIDs and 512m tmpfs. Source closure digest: `d823d507909f161d8e5e2bed23f84dbfee9eb9f820498b68d86c25773f13efef`; semantic workspace SHA-256: `43684307e287bd22d0cfcc91eae2539ba5a3c6d1e1b06a0ef87d4050a5924f88`.
- Actual Context→Containers→Components→Code navigation passed for approve_feature, evaluate_action_dependencies, write_approval_evidence, approval_evidence, _handle_approve_feature and featureApproveActionButton. Each path restored its selected node after reload, opened pinned source, and returned to Components with Level up. Browser provenance showed the clean owned branch at the exact source commit above.
- Render operations remained **1 before / 1 after** all six paths, proving warm artifact reuse without per-view renderer startup. Initial browser readiness took 72.79 seconds; full navigation/reload/source/return paths took 10.28–15.63 seconds each; the total browser run was 152.03 seconds. These are measured host/run observations, not a latency guarantee.

The diagram-impact inventory is reconciled with this planning diff. Unchanged landscape/context/container topology has no new actor, transport, process or data store. Supervisor/team views expose the existing approval responsibility. Approval/Feature/HTTP/dashboard Code views now expose actual entry points; unchanged Watchdog/Boss views still explain admission and delivery. Supplementary approval/evidence diagrams match the source trace: strict dependency refusal precedes writes; authorized success writes document then receipt and requests canonical reconciliation; interruption between writes leaves unknown evidence and uses the existing explicit recovery path. The planned dependency-permissive policy and declaration fence remain child-owned implementation obligations, including reconciliation against the final code diff.

Limits: unrelated operational-panel API requests were stubbed; architecture routes, source resources and rendering were real. Reloads abandoned some requests, producing server BrokenPipeError logs, but all six journeys passed with no observed architecture HTTP error responses. No approval-policy API/Git/browser acceptance or live incident mutation ran in this planning turn. Software/identity admission wiring, evidence compatibility, behavioral acceptance and final diagram updates remain mandatory for feat_056_001/feat_056_002. No unresolved planning-document or architecture-navigation gap remains. Manager final-revision review and human approval remain separate authorities.

## Decision log

- 2026-11-27 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-27 · Epic Architect · **Approval boundary**
  Chose Allow explicit approval with a known, valid, noncancelled incomplete predecessor; preserve unknown/invalid dependency and every independent authorization refusal..
  Rationale: The direct approval path currently conflates ordinary sequencing with authorization. Limit the change to reviewed Feature approval while canonical Watchdog/Boss execution remains gated. Keep strict shared dependency checks elsewhere.
  Honors: Epic success criteria 1 and 2; existing dependency, provider, architecture and software authority..

- `dec_002` · 2026-11-27 · Epic Architect · **Delivery scope and verification**
  Chose Deliver feat_056_001 followed by feat_056_002, with design/Code-view work and bounded API, real-Git and browser evidence inside each Feature..
  Rationale: One backend authority contract followed by its UI consumer provides the smallest coherent delivery. Reuse current receipt, lifecycle state and test fixtures; require architecture reconciliation before plan sign-off.
  Honors: Epic success criteria 3 and 4; frugal-engineering and design skill contracts..

- `dec_003` · 2026-11-27 · Epic Architect · **Approval declaration fence and evidence compatibility**
  Chose Bind a canonical sorted unique depends_on declaration to both scope and exact approval evidence and to the displayed approval request; predecessor lifecycle facts remain outside the approval identity..
  Rationale: The current _revision omits depends_on. Changed declarations must require explicit review, while lifecycle progress must release already authorized work. Extend the existing receipt with a versioned declaration fingerprint; never upgrade an old receipt from today's declaration without immutable historical proof. Unknown proof remains non-dispatchable and requires explicit review.
  Honors: Success criteria 1, 2 and 4; delegated tactical scope mode, corrective exact mode, changed-plan invalidation, restart and concurrency fences..

- `dec_004` · 2026-11-27 · Epic Architect · **Approval component and gate ownership**
  Chose Model the existing approval orchestration as element.component.approval with cascade-approval-code; retain receipt/readiness ownership in element.component.feature-team and execution admission in Watchdog. Require only dependency_incomplete to become approval-permissive; unknown, cancelled and malformed evidence still refuses..
  Rationale: A dedicated in-process component makes authorization, persistence and execution inspectable without inventing a runtime service. The explicit gate matrix records the current HTTP identity and direct software-gate gaps so the backend Feature reuses those existing authorities rather than claiming they are already enforced.
  Honors: Design implementation-depth contract and success criteria 1–4; two existing Features remain sufficient..
## Amendment log

_(none)_
