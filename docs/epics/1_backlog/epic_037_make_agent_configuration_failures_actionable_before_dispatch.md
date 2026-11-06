---
id: epic_037
title: Make agent configuration failures actionable before dispatch
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

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use one pure capability evaluator and one stable reason/remedy vocabulary across brief validation, readiness projection, dispatch, execution preflight, durable blockers, and recovery. Preserve the existing rule that provider discovery never starts a model turn and never persists credentials or raw provider errors. Do not weaken the fresh execution-boundary check merely because an earlier check passed. Treat reviewed model selections and runtime service-tier overrides separately: a convenience action may waive Flex only with explicit human authorization and must not silently substitute a provider, model, or reasoning level. Include the selected document path/revision or equivalent provenance in diagnostics so a stale snapshot cannot masquerade as the operator’s visible configuration. Keep failure responses safe for API/UI display, accessible, restart-safe, and idempotent. Reuse the existing provider inventory, preflight result, blocker, recovery, and dialog infrastructure rather than adding parallel status stores. Preserve automation and manual dispatch through the same gates.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-06 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
