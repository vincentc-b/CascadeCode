---
id: epic_029
title: Pause work when its provider is unavailable
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
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Pause work when its provider is unavailable

## Intent

Epic `epic_028` was activated with Cursor pinned for both planning roles. Cursor is not authenticated on this machine, so both roles repeatedly report `provider startup failed` and the epic appears active without a useful plan. Make provider setup failures a clear, durable state with an operator action, for Epic, Feature, and Task starts. The operator must be able to select another available provider and suitable models for the affected work item, including after activation, without obtaining credentials for a provider they intentionally stopped using.

### Success criteria

- Before activating an Epic or dispatching a Feature or Task, check the effective pinned provider and role models against installed/authenticated provider capability. On a deterministic setup failure, leave the item in its prior column, create no new worktree or checkpoint, and return a structured reason and next step to the War Room. Recheck at the execution boundary because provider availability can change after preflight.
- If credentials or provider availability disappear after work has started, pause further starts for that work item and persist one provider-blocked incident with the work ID, affected roles, provider, safe reason, last attempt, and recommended remedy. Show it on the board and in the room after refresh and restart; never expose credential values or raw provider payloads.
- Show a human-only `Change provider` action on provider-blocked Epic, Feature, and Task rows, including items already in `2_active`. The War Room shows the current provider and per-role models, offers installed/authenticated replacement providers and their supported models, and validates every affected role before submission. Keep a saved unavailable selection visible; do not require the old provider to be authenticated to replace it. For a backlog Epic, this action may open the existing reviewed brief editor; an active item must have a direct recovery path without first returning to backlog.
- Apply an active-item provider change through one serialized, durable recovery operation. Stop or wait for any in-flight turn, recheck ownership and lifecycle gates, record the human's provider/model selection and audit provenance, and reconcile document/runtime settings with checkpoint-pinned provider, model, reasoning, and flex choices before any turn resumes. A restart or partial failure must leave either the old blocked selection or a fully applied new selection, never a checkpoint that silently invokes the old provider. Preserve the reviewed plan, approval state, branch, worktree, transcript, and dirty files. Existing child items retain their own selections; clearly show which future role defaults on the selected item will change.
- After a successful change, offer or start one safe retry on the same work item using the new provider. Resume a compatible checkpoint; when provider-specific turn state cannot be reused, start a fresh role turn with the preserved plan, prior progress, and worktree context. Never reset files, duplicate work, bypass approval/review gates, or treat a provider change as permission to rerun an already completed action. If safe migration is impossible, keep the item blocked with a precise reason and next step.
- Also offer a human retry with the original provider after its setup is repaired. Retry and provider change must be idempotent under concurrent clicks and watchdog ticks and avoid duplicate agent turns or repeated failure toasts. Transient transport failures may use bounded backoff; missing authentication or invalid configuration waits for an explicit change or retry.
- Keep provider selection pinned until a human changes it. Do not silently fall back to another provider or model. Show provider setup, Change provider, and, for an eligible unstarted Epic, Return to backlog as distinct remedies.
- API, board, browser, restart, and lifecycle tests cover missing credential at activation, provider loss after activation, Cursor-to-Codex recovery of an active Epic such as `epic_028`, active Feature and dirty Task migration, stale checkpoint pins, concurrent change/retry requests, restored original credentials, refusal with an in-flight turn that cannot be stopped, and unaffected sibling or child work.

## Macro-architecture

Reuse the effective backend resolver and provider inventory for read-only eligibility and model choices. A human-only recovery command owns the provider change and coordinates lifecycle locks, turn quiescence, durable selection provenance, checkpoint reconciliation, and the normal kickoff/retry path. The board projects the current effective selection and provider-blocked state so the controls survive refresh and restart.

## Cross-module constraints

Reuse provider probes, credential resolution, role/model selection, checkpoint recovery, and the existing War Room health/recovery presentation. Keep startup checks read-only until dispatch is authorized. Treat a human-approved provider change as an explicit operational override, not an edit to reviewed plan prose or an automatic rewrite of child work. Preserve dirty work and prior selection history. Never log secrets, auto-switch providers, require credentials for the abandoned provider, or let a failed provider stall the supervisor or unrelated work.

## Core dependencies

- Existing provider inventory and credential probes, War Room provider/model controls, and model resolution.
- Epic, Feature, and Task checkpoints with pinned role backends, lifecycle locks, and normal kickoff/retry paths.
- Existing backlog brief editor for reviewed edits before activation; Return to backlog remains a separate action for unstarted Epics.

## Feature breakdown

The Epic Team will sequence provider-blocked state and preflight, the human provider-selection and checkpoint migration path for all three tiers, and War Room recovery controls with full lifecycle coverage.

## Open questions

- Which checkpoint fields can be safely rewritten in place, and when must the next role turn be reconstructed from preserved progress?

## Decision log

- 2026-10-31 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
