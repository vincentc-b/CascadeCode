---
id: epic_032
title: change provider ui improvement
tier: epic
status: active
parent: null
children:
- feat_032_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
---
# Change provider UI improvement

## Intent

Replace the free-text `Change provider` recovery prompts with a safe, guided dialog. An operator recovering a provider-blocked active Epic, Feature, or Task should choose only currently usable providers and compatible models through controls consistent with the existing create/edit brief experience, without typing provider IDs or role-to-model JSON.

### Success criteria

1. Clicking `Change provider` on an eligible provider-blocked Epic, Feature, or Task row opens a modal dialog; the flow does not call browser `prompt`.
2. The provider dropdown is populated from the existing normalized inventory of installed/authenticated providers. Selecting a provider renders model dropdowns only for the roles owned by that work tier:
   - Epic: `epic_manager`, `epic_architect`
   - Feature: `feature_lead`, `feature_architect`
   - Task: `swe`
3. Each model dropdown contains only models reported for the selected provider. A provider or model change revalidates dependent model, reasoning, and flex selections using the same behavior as brief creation.
4. Where supported, each role can choose a discovered reasoning override or provider default, and flex mode is offered only for a provider that supports it. Unsupported settings are cleared rather than carried into the request.
5. The current saved provider, models, reasoning, and flex choice prefill the dialog. Unavailable saved values remain visibly identified so the operator understands the blocker, but cannot be submitted as a valid replacement unless they are present in the current inventory.
6. Loading, empty inventory, refresh failure, cancel, and server validation/refusal states are explicit. Cancel makes no change; failed submission keeps the dialog and its selections open; an in-flight request cannot be submitted twice.
7. A valid submission uses the existing human-only provider-recovery endpoint and authoritative recovery command. The server revalidates every affected role before mutation. On success the dialog closes, the board refreshes, and recovery resumes through the existing lifecycle-safe path.
8. Focused UI coverage proves tier-specific role rendering, inventory-backed choices, provider/model dependent revalidation, saved-unavailable display, reasoning/flex behavior, payload construction, cancel, double-submit prevention, and failure retention. Existing recovery API/engine tests remain the proof for authoritative validation, atomic selection/checkpoint updates, and lifecycle safety.

## Macro-architecture

Deliver one vertical War Room feature over existing recovery and inventory contracts.

- **Dialog and controller:** Add a dedicated provider-recovery dialog in the War Room. Opening it receives the selected board item and its safe `provider_recovery.selection` projection, loads the existing brief provider inventory, derives the tier's affected roles, and owns loading, edit, submit, cancel, and error state.
- **Shared selector primitives:** Generalize the existing brief selector module only as needed so provider lookup, model/reasoning capability handling, flex handling, and role-row rendering can accept an explicit role list and labels. Brief create/edit behavior remains unchanged. Recovery code composes those primitives rather than maintaining another provider/model catalog.
- **Submission boundary:** Build the existing recovery payload shape—`provider`, role-scoped `models`, optional role-scoped `reasoning`, and `flex_mode`—and POST it to `/api/provider-recovery/{work_id}/change`. The current recovery route and command remain the trust and mutation boundary; client validation exists for usability only.
- **Refresh and errors:** Reuse the inventory refresh path for recoverable discovery failures and the board refresh path after success. A rejected POST renders its safe reason in the modal without discarding the operator's current choices.

No new provider API, recovery endpoint, persistence format, background refresh service, or generic form framework is required.

## Cross-module constraints

- Provider/model options must come from the existing normalized discovery inventory; do not add static UI catalogs or accept arbitrary replacement text.
- Render and submit exactly the roles owned by the target tier. Do not modify child items or roles outside the active item.
- Preserve the existing server-side capability preflight, human authorization, lifecycle quiescence, atomic document/checkpoint reconciliation, retry semantics, and blocker clearing rules.
- Keep unavailable saved choices visible for diagnosis, while treating current inventory plus server revalidation as authoritative for a replacement.
- Do not expose credentials, raw provider responses, or unsafe errors to the browser or logs.
- Keep `Provider setup`, `Retry provider`, Return to backlog, and brief create/edit behavior unchanged.
- Maintain keyboard-accessible modal semantics, labeled controls, an announced status/error region, deterministic initial focus, and focus return to the invoking action.
- Prefer focused browser/controller cases plus the existing recovery integration coverage; do not duplicate lifecycle tests at the DOM layer.

## Core dependencies

- `cascade/war_room/static/war_room.js`, `cascade/war_room/templates/war_room.html`, and `war_room.css`: current row actions, prompt-based change flow, dialog markup, and presentation.
- `cascade/war_room/static/brief_defaults_ui.js`: existing provider/model/reasoning/flex selection and rendering behavior to reuse or narrowly generalize.
- `GET /api/brief/inventory` and `POST /api/brief/inventory/refresh`: normalized, fault-isolated inventory and explicit refresh.
- Board row `provider_recovery.selection`: safe persisted provider, models, reasoning, and flex values used for prefill.
- `POST /api/provider-recovery/{work_id}/change` and the existing recovery command/engine: authoritative validation, mutation, checkpoint reconciliation, and kickoff.
- Existing War Room JS case harnesses and provider recovery API/engine tests.

## Feature breakdown

1. **feat_032_001 — Inventory-backed provider recovery dialog**
   - Replace prompt/JSON entry with the dedicated dialog for provider-blocked active Epic, Feature, and Task rows.
   - Reuse generalized brief selector primitives with an explicit tier role set, including reasoning and flex capability handling.
   - Preserve saved-unavailable visibility, recoverable inventory states, selections on failure, and guarded submission.
   - Submit through the existing recovery endpoint and verify the complete UI-to-recovery handoff with focused tests.

This is one shippable slice. Splitting selector refactoring from the dialog would create no independently valuable outcome, while changing the recovery engine is unnecessary because it already validates and applies the submitted selection safely.

### Validation and delivery boundary

Use focused JavaScript cases for selector state and modal/controller behavior, a rendered-page assertion for the dialog and script wiring, and the existing HTTP tests to confirm the submitted shape remains server-validated. Add one representative flow that opens recovery for each tier or parameterizes the tier-role mapping, changes provider/model, submits once, and verifies success refresh versus failure retention. Avoid duplicating checkpoint, concurrency, or lifecycle suites already owned by provider recovery.

Out of scope: changing provider discovery or authentication, adding providers/models/roles, editing unblocked work, changing backlog brief editing, redesigning the Providers pane, altering automatic retry/backoff, changing checkpoint migration, or propagating a selection to children.

## Open questions

_(none)_

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-03 · Epic Manager · **Scope and delivery**
  Chose Deliver one vertical feature, feat_032_001, that replaces the prompt/JSON recovery flow with an inventory-backed modal for active Epic, Feature, and Task rows; leave provider discovery and the recovery engine unchanged..
  Rationale: The operator outcome is incomplete without the full dialog-to-recovery handoff. Existing inventory and recovery boundaries already solve discovery and safe mutation, so extending them would add cost without serving the brief.
  Honors: The approved request for brief-like provider/model dropdowns, frugal engineering, and the existing provider recovery safety contract..

- `dec_002` · 2026-11-03 · Epic Manager · **Selection and validation contract**
  Chose Reuse and narrowly generalize the brief selector primitives for an explicit tier-specific role list, show saved unavailable values for diagnosis, and permit submission only from current inventory while retaining authoritative server revalidation..
  Rationale: One shared capability-driven behavior prevents UI catalog drift, keeps the active item's current blocker understandable, and does not mistake client controls for a security or correctness boundary.
  Honors: Valid provider/model choices, parity with create-brief behavior, affected-role isolation, and no silent fallback..
## Amendment log

_(none)_
