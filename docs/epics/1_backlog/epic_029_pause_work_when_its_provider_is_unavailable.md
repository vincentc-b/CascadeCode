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
flex_mode: true
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Pause work when its provider is unavailable

## Intent

Epic `epic_028` was activated with Cursor pinned for both planning roles. Cursor is not authenticated on this machine, so both roles repeatedly report `provider startup failed` and the epic appears active without a useful plan. Make provider setup failures a clear, durable state with an operator action, for Epic, Feature, and Task starts. A missing credential or unavailable provider must not cause repeated model turns that cannot succeed.

### Success criteria

- Before activating an Epic or dispatching a Feature or Task, check the effective pinned provider and role models against installed/authenticated provider capability. On a deterministic setup failure, leave the item in its prior column, create no new worktree or checkpoint, and return a structured reason and next step to the War Room. Recheck at the execution boundary because provider availability can change after preflight.
- If credentials or provider availability disappear after work has started, pause further starts for that work item and persist one provider-blocked incident with the work ID, affected roles, provider, safe reason, last attempt, and recommended remedy. Show it on the board and in the room after refresh and restart; never expose credential values or raw provider payloads.
- Offer a human retry after the provider becomes usable. Retry must be idempotent under concurrent clicks and watchdog ticks, resume the existing branch/worktree/checkpoint when safe, and avoid duplicate agent turns or repeated failure toasts. Transient transport failures may use bounded backoff; missing authentication or invalid configuration waits for an explicit change or retry.
- Keep provider selection pinned. Do not silently fall back to another provider or model. Point the operator to provider setup or, for an eligible unstarted Epic, the separate Return to backlog action.
- API, board, browser, restart, and lifecycle tests cover missing credential at activation, provider loss after activation, bounded retry, restored credentials, and unaffected sibling work.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse provider probes, credential resolution, role/model selection, checkpoint recovery, and the existing War Room health/recovery presentation. Keep startup checks read-only until dispatch is authorized. Preserve dirty work and current provider/model pins. Never log secrets, auto-switch providers, or let a failed provider stall the supervisor or unrelated work.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-31 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
