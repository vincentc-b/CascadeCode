---
id: epic_037
title: Make agent configuration failures actionable before dispatch
tier: epic
status: active
parent: null
children:
- feat_037_001
- feat_037_002
- feat_037_003
- feat_037_004
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
# Make agent configuration failures actionable before dispatch

## Intent

Prevent lifecycle work from starting with an agent configuration that is already known to be invalid, and make every provider or model refusal understandable and recoverable from the War Room. Validate the complete effective role configuration at the earliest safe boundary, retain a fresh just-in-time check before each provider process starts, and present structured per-role failures instead of opaque codes such as `provider_preflight_blocked`. When Flex is the only incompatibility, let a human explicitly continue without Flex through one small, audited, idempotent action.

### Success criteria

1. **Front-load the complete role stack.** Brief creation/edit validation and Epic activation evaluate every currently pinned role (`epic_manager`, `epic_architect`, `feature_lead`, `feature_architect`, and `swe`), not only the roles started at that boundary. Feature and Task configuration overrides are checked when they are introduced and before their parent plan can authorize downstream work. A deterministic failure creates no lifecycle event, worktree, queue entry, checkpoint advance, or provider turn.
2. **Keep a fresh execution check.** Every actual Epic, Feature, and Task provider invocation refreshes capability immediately before process startup, using the same canonical evaluator as dispatch. This catches provider catalog, authentication, service-tier, and local CLI/tool-host drift without duplicating or contradicting the earlier result.
3. **Return one structured failure contract.** Dispatch/readiness APIs report safe per-role results including role, provider, model, reasoning level, Flex selection, configuration source/revision, stable reason code, deterministic-versus-transient classification, inventory freshness, and eligible remedies. Human-readable summaries lead with language such as “Selected agent configuration is not supported”; internal codes remain available only as details.
4. **Show an actionable War Room dialog.** Epic activation, Feature dispatch, approval-driven dispatch, and Task retry render the structured failure in an accessible modal or equivalent focused panel. It identifies every affected role, explains what changed or is missing, and offers only valid actions: refresh and retry, open provider setup, choose a supported configuration, or continue without Flex. The raw `provider_preflight_blocked` string is never the sole operator feedback.
5. **Support one-click “Continue without Flex.”** When all deterministic failures are `flex_mode_not_supported` and the same selections pass otherwise, a human can disable Flex, persist a non-secret authorization/audit record, revalidate against fresh inventory, and retry the original action exactly once. The action preserves reviewed plan content and existing work, cannot mask another blocker, and cannot duplicate worktrees, dispatch events, checkpoints, or model turns.
6. **Expose readiness before the click.** Backlog and active rows project current agent-configuration readiness and inventory age from the same evaluator used by dispatch. Warnings distinguish an invalid selection from a transient provider outage and clearly say when the result may be stale. Refreshing inventory updates the projection without mutating lifecycle state.
7. **Cover the failure matrix.** Tests and operator messages cover missing or malformed role/provider/model configuration; unavailable or empty discovery; provider not installed or authenticated; provider temporarily unavailable; model retired/not offered; unsupported reasoning effort; provider- or model-level Flex rejection; unsupported provider adapter; incompatible CLI/SDK or required MCP/tool-host capability; late child overrides; stale document/snapshot provenance; and capability drift between early validation and execution.
8. **Make blockers durable and recoverable.** A failed start records one restart-safe incident per work item, updates rather than spams repeated failures, preserves first/last observation and affected roles, and clears only after a successful fresh check. Deterministic failures require a valid configuration change or narrowly eligible override; transient failures retain bounded retry/setup actions.
9. **Remove silent fall-throughs.** Missing legacy selections and model/config resolution errors are surfaced as explicit configuration blockers rather than bypassing preflight and failing later. Backward compatibility is handled by an actionable migration/default path, not by silently accepting an incomplete selection.
10. **Verify end to end.** Browser/API tests prove an invalid future Feature or Task role is caught during Epic activation, the dialog renders every failed role and remedy, “Continue without Flex” performs one successful retry, transient retry remains distinct, stale inventory is refreshed, and a catalog change after activation is still caught safely immediately before execution.

## Macro-architecture

Extend the existing configuration and recovery pipeline. The boundary owns inventory refresh and lifecycle effects; the evaluator accepts normalized selections and capability observations and remains pure.

1. **Effective selections and evidence.** Reuse `watchdog/model_resolve.py`, `brief_stack.py` and `work_backend.py` to produce the same selections that child minting and execution consume. Epic checks cover all five pinned roles; Feature checks cover its two planning roles plus effective SWE; Task checks cover SWE. Existing child overrides are checked when introduced and before the parent authorizes them. Resolve from the owning worktree and retain per-field source, document path/revision and a selection fingerprint. Explicit malformed selections and incomplete legacy pins are configuration blockers with a supported migration/default path; they must not disappear into a resolver exception or an empty successful batch.
2. **One evaluator and result contract.** Extend `agent/preflight.py` and the normalized discovery types. A batch identifies work item/action, outcome and inventory freshness; each role result identifies role/tier, provider, model, reasoning/default, requested/effective Flex, provenance, stable reason code, safe message, classification and eligible remedies. Retain every role failure, with deterministic failure taking batch precedence over transient unavailability. Installation, authentication, empty discovery, temporary outage, unsupported adapter and CLI/SDK/tool-host compatibility need distinct safe evidence and remedies. Capability probes remain outside the pure evaluator and cannot start a model turn.
3. **Admission and execution.** Brief writes, child configuration writes, activation, dispatch, approval and retry call the same evaluator before irreversible lifecycle work. Parent approval validates existing downstream selections before setting new approval state. Manual and automated paths share these gates. Every actual process launch additionally refreshes inventory and checks the authorized execution selection/provenance. Stale snapshots require reconciliation through the existing configuration/recovery path, never silent replacement. Discovery failure blocks the start and offers bounded recovery; it does not masquerade as an invalid model.
4. **Durable incident and projection.** Extend `agent/execution_preflight.py` and `provider_recovery_state.py` to retain the complete affected-role result in the existing one-incident-per-work-item record. Failed admission/launch may update this diagnostic record but cannot create a lifecycle event, worktree, queue entry, execution checkpoint advance or model turn. Preserve first/last observation on repetition and restart. Only a fresh successful evaluation of the entire blocked scope resolves it. Readiness uses the same evaluator with the existing bounded cache; it does not create incidents or mutate lifecycle state. Report age/staleness explicitly and do not persist process-relative monotonic values as portable timestamps.
5. **Narrow Flex continuation.** Extend the existing recovery command, ledger and lifecycle gate. A server-validated human request binds the original action, revision, selection fingerprint and affected scope. Eligibility requires at least one Flex rejection and a fresh, fully supported evaluation of the same selections with Flex disabled; mixed remaining failures block it. Persist a runtime Flex waiver separately from reviewed plan text and model/reasoning/provider pins. Scope it to the original action's validated role stack and normal stamped descendants; independent overrides and existing sibling work remain independent. New selections/revisions require revalidation and fresh authorization. Replay through ordinary lifecycle/dependency/review gates exactly once in the successful path.
6. **Safe retry handoff.** The recovery ledger records authorization and pending/completed action outcomes. A repeat click or restart consults the same action identity and receipt; it cannot issue a second dispatch or turn. Resolve the crash window between recording authorization and kickoff through durable replay/claim evidence in the existing command path. Ambiguous handoff stays blocked with actionable status instead of blind replay. A later capability refusal preserves the incident and existing work. The feature must specify receipt transitions before implementing replay.
7. **Operator surface.** Extend War Room serialization, dispatch/approval adapters, board rows and `provider_recovery_dialog_ui.js`. Render every failed role and source revision, readable safe text, freshness and server-computed eligible actions. Keep agent readiness distinct from plan/dependency readiness. Inventory refresh reprojects rows and dialog state without lifecycle mutations. Preserve keyboard access, focus restoration and safe text rendering.

### Verification and scope limits

Use one table-driven capability/selection matrix, targeted lifecycle integration tests for side-effect ordering and durable recovery, and a small set of browser/API flows for operator behavior. Reuse existing preflight, brief-stack, approval, recovery and browser fixtures with fake discovery/process boundaries; do not make live model turns part of tests. Required flows include future Feature/SWE rejection at activation, late child override, all-role diagnostics, stale inventory, post-activation drift, transient retry, and one successful Flex continuation with repeated-click/restart evidence.

No new provider integration, automatic model/provider/reasoning substitution, dependency installation, general retry scheduler, parallel status store, board redesign or unrelated lifecycle cleanup is included. Missing local runtime prerequisites lead to setup guidance; this epic does not authorize installing/upgrading them.

## Cross-module constraints

Use one pure capability evaluator and one stable reason/remedy vocabulary across brief validation, readiness projection, dispatch, execution preflight, durable blockers, and recovery. Preserve the existing rule that provider discovery never starts a model turn and never persists credentials or raw provider errors. Do not weaken the fresh execution-boundary check merely because an earlier check passed. Treat reviewed model selections and runtime service-tier overrides separately: a convenience action may waive Flex only with explicit human authorization and must not silently substitute a provider, model, or reasoning level. Include the selected document path/revision or equivalent provenance in diagnostics so a stale snapshot cannot masquerade as the operator’s visible configuration. Keep failure responses safe for API/UI display, accessible, restart-safe, and idempotent. Reuse the existing provider inventory, preflight result, blocker, recovery, and dialog infrastructure rather than adding parallel status stores. Preserve automation and manual dispatch through the same gates.

## Core dependencies

- Existing provider discovery/inventory cache and provider adapters supply normalized capability evidence; extend these contracts rather than introducing another discovery subsystem.
- Existing resolution/stamping, owning-worktree document resolution, approval/dispatch and Epic/Feature/Task launch paths must agree on selection provenance.
- Existing durable blockers, provider recovery ledger, lifecycle admission gate and kickoff machinery provide incident storage and retry coordination.
- Existing War Room provider routes/dialog, board serialization and browser/API test harness provide the operator surface and validation.
- No separate external epic dependency or package installation is required by this plan. Feature dependencies below serialize changes to the shared contract and lifecycle seams.

## Feature breakdown

| Order | Feature | Depends on | Required outcome / success criteria |
| --- | --- | --- | --- |
| 1 | feat_037_001 — Unify effective role configuration and capability diagnostics | None | Shared selection/provenance contract, pure evaluator and complete failure/remedy matrix; criteria 1–3, 7, 9. |
| 2 | feat_037_002 — Enforce complete configuration gates and durable start blockers | feat_037_001 | Front-loaded validation, fresh launch checks, structured approval/dispatch failures and one durable incident; criteria 1–3, 7–9. |
| 3 | feat_037_003 — Add human-authorized idempotent continuation without Flex | feat_037_002 | Audited runtime waiver plus original-action retry with revision/concurrency/restart protection; criterion 5 and recovery constraints in 2, 3, 7, 8. |
| 4 | feat_037_004 — Expose actionable War Room diagnostics and readiness | feat_037_003 | Accessible all-role dialog, row readiness, valid actions and final browser/API flows; criteria 3, 4, 6, 10. |

Each feature owns its focused regression tests. Feature 4 verifies the integrated operator experience, not a second exhaustive copy of the evaluator matrix. All ten success criteria remain required for epic completion. Feature teams refine data/API contracts and tasks within these boundaries; they must propose an epic amendment for contract changes.

## Open questions

None outstanding for product scope. The initial implementation-risk question is resolved by the following sequencing constraints:

- Feature 1 fixes effective-role resolution, source/revision semantics, capability evidence and the reason/remedy contract before downstream integrations start.
- Feature 2 proves refusal precedes lifecycle side effects and that pinned child/execution provenance is checked at every authorization boundary.
- Feature 3 specifies runtime-waiver scope/invalidation and durable retry receipt transitions before mutation/replay implementation; reviewed plan hashes and existing work must survive.
- Features use the existing test harness and fake provider evidence. No dependency installation or live provider credential access is needed to establish these contracts.

## Decision log

- 2026-11-06 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
