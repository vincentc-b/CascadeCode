---
id: feat_047_002
title: Admit late repair generations without losing accepted review history
tier: feature
status: completed
parent: epic_047
children:
- task_047_002_001
- task_047_002_002
- task_047_002_003
- task_047_002_004
depends_on:
- feat_047_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 39558b2cb130000418f59b6a2683fc28c7038d56
created: '2026-11-18'
updated: '2026-11-24'
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
approved_at: '2026-11-24T05:38:26.227282+00:00'
---
# Admit late repair generations without losing accepted review history

## Parent Epic

[epic_047](../../epics/2_active/epic_047_recover_late_repair_delivery_after_feature_completion.md), pinned at parent_rev in frontmatter. Own epic criteria 1–4, 7 and 10. The approved boundary retains exact owner resolution and descendant survival from feat_047_001, and leaves parent/audit routing and full journey evidence to feat_047_003/004.

## Scope

Admit an in-scope repair under an active, open-review-staged or accepted Feature while preserving its original Task identity, committed work, action attempts and historical review acceptance. A completed board column alone is not proof of current operational terminality. One generation-bound operation supplies the legal parent route; mint, delivery, publication and closeout consume it under existing locks. Refuse unknown ownership/forge facts, changed scope, absent approval or an ineligible Epic target with a typed owner and next action. No new scheduler, queue, lifecycle store, general reopener, duplicate Task or automatic ancestor reactivation.

## Data structures

- Versioned `feature_repair` action metadata in the existing tracking-root `.cascade/executions.json`: stable action ID from Feature ID plus queued Task delivery action ID, or a reserved mint-request ID; request/Feature/Task/Epic IDs; exact product and tracking owner fingerprint; generation and SHA-256 gate fingerprint; claim and live owner; approval/scope references; prior and intended document path/digest; source and target refs/heads and final-validation reference; prior review identity/accepted heads; required publication generation/route; phase, typed blocker, authority event ID, introduction commit/blob and postcheck references. Keep all generations and attempts; missing legacy facts remain unknown. Phases are prepared, authority_recorded, parent_enabled, delivery_pending, review_pending, integration_pending, retirement_pending and verified, or a typed blocked/superseded outcome. These are action phases, not board statuses.
- `FeatureRepairAuthorized` is a dedicated canonical Feature-queue event, keyed by action ID and generation, binding owner, parent, source/target, intended active path and document digest. It is meaningful only with the matching live prepared action. The committed active introduction is bound to the same action and generation.
- Versioned Feature review registry entry retains immutable `generations` and a `current_generation` projection. Each generation binds repair/action generation, route, URL/forge ID, source and target refs and observed SHAs, accepted merge SHA, publication action ID and reconciliation status. Existing top-level fields remain a compatibility read projection; they cannot satisfy a later generation. Legacy generation zero is created only from proven stored and live forge facts.
- A current-obligation predicate distinguishes child delivery, exact review acceptance, parent integration and checkout survival. It is consumed by every closeout path and the descendant-aware retirement proof. Old review callbacks update their own generation only.

## API contracts

- The canonical Feature repair operation exposes inspect/admit/resume semantics for an exact Feature and existing Task delivery action or reserved mint request. It returns action ID, generation, phase, typed refusal or next action and evidence references. Callers use authenticated Feature, immediate Epic or admitted audit context; no caller-provided role string grants authority. Same request replays the same identity. A changed owner/generation/approval/head fails closed or routes through supported synchronization; observation alone creates no new obligation.
- Admission takes bounded Git/forge observations outside the critical section. Under the tracking-root task_lifecycle_lock (process lock then flock), re-read exact mutation owner, parent, approval, comments, dependencies, action, validation pair, checkout cleanliness and execution lease. Persist and sync prepared intent and reserved child identity before a move or mint. Append and sync the authority event before active-path introduction; commit the exact owner document with action/generation identity; checkpoint the introduction commit/blob. Recheck the claim and current gates after external work. Keep review/registry locks short and never acquire lifecycle lock while holding them. Live execution owners remain fenced.
- The watchdog accepts a repair introduction only when event, live action generation, exact owner/root/path and intended or committed blob/commit agree. The move/checkpoint gap uses the prepared receipt and fenced exact blob. It rejects stale/mismatched receipts through the existing unauthorized-active path without fabricating FeatureReadyToPlan. Queue pruning retains authority while the repair is active or outstanding.
- Minting under a completed Feature first reserves an idempotent child identity and establishes the legal parent delivery route, then writes the Task and parent child list. It refuses unresolved blocking comments, missing plan/revision approval, unmet dependencies, dirty/protected or missing checkouts, live leases, unknown owner/review or ineligible Epic. Active parents continue through ordinary admission. A crash replays the same child/spec digest.
- Task recovery uses the original Task checkout and queued delivery action. Compare both source and target heads to the recorded final-validation pair immediately before rearming or merging. If either moved, use existing branch synchronization and Task final validation, preserving prior evidence and replacing the current pair only after green tests. A document commit that moves the target also invalidates the pair. Do not redispatch an unchanged validated implementation to fix parent status.
- Open-review repair can reuse the URL only after fresh forge evidence proves it remains open against the intended target. Accepted review records and heads remain immutable; later code requires a distinct linked follow-up review of the retained Feature branch against its owning Epic branch. Unknown or inconsistent legacy facts refuse. Existing publication/rebase and stacked-review recovery gates still apply.
- One completion predicate, checked under the lifecycle lock before the already-completed fast path, requires all admitted children terminal with current delivery evidence, no prepared admission or live delivery, current review generation accepted at its published source/target heads, independent integration proof, and current comments/approvals/dependencies/architecture gates. Review-disabled mode requires explicit local integration evidence. If closeout wins first, later admission starts a new obligation; if admission wins, closeout defers. Retirement consumes the same current-obligation result and feat_047_001's descendant proof.

## Logic flow

```mermaid
sequenceDiagram
  participant Caller as Scoped Feature/Epic/audit caller
  participant Action as Existing action ledger
  participant Queue as Feature queue
  participant Board as Owning Feature document
  participant Task as Original Task delivery
  participant Review as Review registry and forge
  participant Boss as Closeout and retirement
  Caller->>Action: inspect exact owner and current gates
  Caller->>Action: prepare/claim generation under lifecycle lock
  Action->>Queue: append FeatureRepairAuthorized
  Queue->>Board: enable exact active introduction
  Board->>Task: sync/revalidate if either head moved
  Task->>Review: publish current open/follow-up obligation
  Review->>Boss: reconcile exact accepted heads
  Boss->>Action: verify children, integration and survival
  Note over Action,Boss: Restart resumes the same action; stale owner, lease or head blocks advancement
```

Persistent state: the action ledger, queue event, committed Feature/Task documents, Task validation/delivery records and review registry. A crash before authority leaves no active path; after authority or move, replay recognizes the exact event and document effect; after review save or acknowledgement, reconciliation reads the same generation. Network, tests and provider calls occur outside the lifecycle lock and are fenced on return.

## Task breakdown

| Task | Purpose | Depends on |
|---|---|---|
| task_047_002_001 | Durable generation, authority event, exact active introduction and watchdog replay. | None |
| task_047_002_002 | Idempotent late mint, review-generation state and current closeout gate. | task_047_002_001 |
| task_047_002_003 | Preserve and revalidate the original Task delivery; publish/reconcile open or follow-up review at exact heads. | task_047_002_002 |
| task_047_002_004 | Core race/restart regressions and final design/model reconciliation. | task_047_002_003 |

Every Task includes a normal and a refusal or resume path through production gates. Task frontmatter contains the same dependency edges.

## Diagram-impact inventory

| Level / view | Owning design and source | Required Task update and check |
|---|---|---|
| Landscape/context: `cascade-landscape`, `cascade-context` | Root DESIGN.md; current operator, forge and provider boundaries | No topology change: the repair uses existing actors. Final Task verifies this against the diff. |
| Containers: `cascade-containers` | Root DESIGN.md and cascade/DESIGN.md | No new process/store: action and review records stay in existing repository/runtime containers. Final Task checks the rendered view and source links. |
| Components: `cascade-supervisor-components`, `cascade-team-components` | cascade/{feature,boss,task,watchdog}/DESIGN.md | Show Feature repair, Boss closeout/review, Task validation and Watchdog authority collaboration if existing edges do not explain the final implementation. Final Task reconciles both views and design links. |
| Code: `cascade-feature-code`, `cascade-task-code`, `cascade-boss-code`, `cascade-watchdog-code` | Same owning designs; actual action/mint, validation, closeout/review and authorization symbols | Tasks 1–3 update their owning Code nodes and source contract with real sourcePath/sourceSymbol and declaration kind. Task 4 checks cross-view navigation and stale symbols; coordinate Watchdog ownership with feat_047_003. |
| Behavior | Owning child designs and cascade/DESIGN.md | Tasks 1–3 add source-linked state/sequence diagrams with input/output, persisted state, normal flow, failure gates and restart/resume. Task 4 traces one normal and one refusal/replay path. |

Validate model/source contract, supported pinned local render, checkout-relative links, context→container→component→Code Explore, Level up, deep-link restoration and representative pinned source. Preserve accepted model snapshots and use the revision-pinned publication workflow; report measured rendering/navigation evidence without a latency promise.

## Planning design review

At plan sign-off, reviewed DESIGN.md, cascade/DESIGN.md, cascade/{feature,task,boss,watchdog,workspace}/DESIGN.md, the model/views/source contract and mint, action, rollup, review and watchdog entry points. The implementation Tasks own the source-linked updates, normal/refusal/restart diagrams and final publication checks listed above. Planning verification inspected the source contract's view keys and code-node inventory and checked the owned worktree was clean before board writes; that planning check did not include a render, browser navigation, forge acceptance or new lifecycle test. Task 4 records the exact implementation revision, checks, design edits and gaps after delivery.

All four Tasks are merged. Task 001's completed spec retains generated placeholder acceptance and test sections. The scoped revise_task tool cannot revise a completed Task; its delivered behavior is judged against Task 1's allocation in this plan and the implementation evidence below. Tasks 002–004 have complete scoped acceptance and test plans.

## Risks & upward questions

A terminal Epic or missing integration target is an explicit higher-owner/operator prerequisite; this Feature does not reopen it. Forge state may change between observation and commit, so every phase rechecks fresh facts and claim. The review registry retains generations within one Feature record, and current child, review and integration obligations gate the completed path. No epic amendment is currently required.

## Decision log

Decisions are appended with record_decision.

- `dec_001` · 2026-11-24 · Feature Architect · **Data structures / API contracts**
  Chose Use one generation-bound feature_repair action in the existing execution ledger and a dedicated FeatureRepairAuthorized event for exact active-path authority..
  Rationale: A prepared action and event precede the document move; their owner, generation and document binding allow idempotent replay while preserving unauthorized-active detection and prior attempts.
  Honors: epic_047 criteria 1–3 and final transaction contract; existing lifecycle lock and scoped tool authority..

- `dec_002` · 2026-11-24 · Feature Architect · **API contracts / Task delivery**
  Chose Keep the original Task and queued delivery action; revalidate both tested heads through the existing Task final gate before rearming when either head moves..
  Rationale: The missing parent route does not invalidate committed implementation, but an old validation pair cannot prove a changed source or target. Preserving history makes recovery auditable.
  Honors: epic_047 criterion 4; original Task identity, execution lease and final-validation gates..

- `dec_003` · 2026-11-24 · Feature Architect · **Data structures / Completion and review**
  Chose Store immutable review generations with one current obligation, and check current child, review and integration evidence before every completed-parent closeout path..
  Rationale: A merged historical review covers its accepted heads only. Generation-aware callbacks, publication and closeout prevent later repair code from inheriting old approval or being retired prematurely.
  Honors: epic_047 criteria 7 and 10; existing forge publication and descendant-safe retirement contracts..

## Closeout

Completed child work: `task_047_002_001` (Persist repair generation and authorize exact Feature reactivation), `task_047_002_002` (Gate child mint and closeout on current repair and review generation), `task_047_002_003` (Revalidate original Task delivery and publish the correct review), `task_047_002_004` (Prove repair replay and reconcile integrated architecture views). All four are in `3_completed`.

The delivered repair binds a prepared action, authority event and committed Feature introduction to one generation. Late mint reserves one child identity; original Task delivery retains its action and revalidates moved source or target heads. Review generations preserve accepted history while closeout checks the current child, review and integration obligation. Task 004's deliverable revision was `0f15b03a922334c9e53599bed61f899b4f5c718a`; the Feature integration branch contains the Task merge at `a754b29a` before the closeout commits.

Verification: supervised final validation reported 88 passing tests in 71.30 seconds against Feature base `4f09d4237cd97122357cfdcc494fd1132facef9a`, covering repair and mint replay, review generations, Task queue, Boss rollup, C4 source/render adapters, architecture HTTP and navigation UI. Task 004 validated the source contract (151 elements, 166 relationships, 24 views) and renderer/HTTP/UI paths, including pinned source, Level up, deep links and cache behavior. Accepted architecture snapshots were not rewritten. No runtime deployment is asserted.

Design review: `cascade/feature/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/boss/DESIGN.md` and `cascade/watchdog/DESIGN.md` were reconciled with the final diff; `cascade/DESIGN.md` was reviewed and needs no durable change because its repair/review boundary remains accurate. The Watchdog design now states the generation-bound Feature repair authority. Landscape/context (`cascade-landscape`, `cascade-context`) retain the same operator, forge and provider boundaries; containers (`cascade-containers`) retain the supervisor and repository stores; component views (`cascade-supervisor-components`, `cascade-team-components`) retain the same collaborators. Integrated Code views `cascade-feature-code`, `cascade-task-code`, `cascade-boss-code` and `cascade-watchdog-code` were reconciled to source symbols and declaration kinds; Task validation and Watchdog authority nodes were added. Normal repair and refusal/resume paths are described in the owning designs and exercised by focused tests. Source-contract validation, pinned rendering and representative navigation passed.

Evidence gaps: Task 001's completed spec still has generated `TBD` acceptance and test sections; the scoped revision tool cannot edit a completed Task. The Feature plan and delivered Task 001 code/tests provide the reviewable contract and implementation evidence, but do not repair that historical Task record. Known baseline limits reported by Task 004 are three stale frozen-artifact/design-evidence failures in `tests/architecture/test_final_reconstruction_validation.py`, two pre-existing trunk-copy completion assertions in `tests/task/test_delivery_blocker_validation.py`, and provider-preflight blocks in parts of `tests/watchdog/test_watchdog.py`; these were outside its focused final validation.

Architecture publication handoff: The final integrated Code-view and source-contract edits are committed on the Feature branch, while the model fragments declare `epic_047` as their architecture owner. The earlier `no_diagram_change` publication covers only the planning revision `adee5617fd3c69527f9b7d8ac199edca10c9f99c`. At this closeout, `epic/epic_047` does not contain the Feature's model edits, so the final diagram change has no owner-published review at its integrated Epic revision. After Feature integration, the Epic Architect must pin the committed design and model closure, publish against the current accepted-lineage generation, and complete its architecture review. The local contract/render/navigation checks above verify the delivered proposal but do not establish architecture acceptance.
