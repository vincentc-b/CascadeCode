---
id: feat_051_002
title: Admit durable scoped repairs for open Feature reviews
tier: feature
status: completed
parent: epic_051
children:
- task_051_002_001
- task_051_002_002
- task_051_002_003
- task_051_002_004
depends_on:
- feat_051_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: c4a9ef2534f34d5955bd5e18ed837087f649ac18
created: '2026-11-26'
updated: '2026-11-26'
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
approved_at: '2026-11-26T21:25:36.564487+00:00'
---
# Admit durable scoped repairs for open Feature reviews

## Parent Epic

epic_051

## Scope

Provide one guarded request → admission → wakeup → repair route for direct-parent and authenticated human fix requests against the existing open Feature review. Extend feature/repair.py and the current action ledger; do not require an unrelated Task lifecycle mismatch to admit a review repair. Route team_supervision.py and epic/recovery.py through this adapter. Integrate existing human mutation entry points, Feature scoped tools, mint_task/reserve_repair_child, publication and Watchdog authorization/independent postchecks. Keep a request acknowledgement distinct from executable admission, execution and verified outcome.

Persist request identity, scoped reason/evidence, accountable Feature, original review URL/forge/source-target route, observed head pair, repair generation, approval/scope authority, claim and existing budget identity before scheduling. Recheck mutable gates under the current lifecycle/owner lock. Reuse request and reserved child on replay; same request ID with changed content refuses. Concurrent requests/turns must join or defer to one current owner, never create competing writers. Stale head/generation/owner evidence refuses or requests fresh observation. Missing approval, unresolved governing comments, changed scope, dependencies, cancellation, exhaustion or unavailable forge evidence produce a typed next prerequisite; legitimate scoped review response must not need a human to resolve its own fix request before work can begin. Broader changes use existing amendment/approval paths.

Acceptance: implementation-complete/open-red-PR + parent fix request becomes a durable admitted generation, resumes the retained Feature, mints/dispatches a scoped repair Task through normal guarded tools and refreshes the same PR. Human and parent requests converge on that adapter. Crash after admission/before enqueue, after enqueue/before checkpoint and during child reservation resumes exactly once. Typed results expose requested/admitted, acknowledged, executing/executed, refused/waiting, verification pending/verified and the next prerequisite with action/generation identity. Legacy completed-open Feature follows supported repair reconciliation, not a manual board edit. Existing accepted/merged-review follow-up behavior remains outside this open-review route. Independent postcheck binds corrected source, current required-check evidence, accepted review generation and intended-target integration before verified outcome/retirement. Claims and finite incident/provider/validation budgets survive restart and cannot reset on duplicates.

Tests: feature repair, Epic direct-parent recovery, kickoff, mint reservation, publication safeguards and parent lifecycle postcheck suites; use fault injection at durable boundaries and a concurrent worker case, not mock-only state assertions. Design owners: cascade/feature/DESIGN.md (repair), cascade/epic/DESIGN.md (parent API), cascade/watchdog/DESIGN.md (independent postcheck), cascade/task/DESIGN.md only if its contract changes. Views: cascade-feature-code, cascade-epic-code, cascade-watchdog-code and affected cascade-task-code/cascade-teams-code. Trace actual feature_repair, reserve_repair_child, mint_task, recover_feature, supervise_child, repair_event_authorizes and postcheck symbols. Extend existing REQ-FEATURE-REPAIR-001/002 and shared review/owner contracts without duplicating them.

### Required Task acceptance and design handoff

Feature planners must carry the relevant acceptance cases below into executable Task specifications. Tasks update the owning DESIGN.md, affected parent/consumer links, model.dsl, views.dsl and workspace.contract.json together where behavior changes. Stable requirement/decision IDs have exactly one design owner. Preserve the existing revision-pinned architecture review workflow and accepted artifacts. Each changed component needs a native Structurizr Code view with real source paths/symbols, correct declaration kinds, and matching cascade.codeComponent/cascade.parent metadata. Record normal and failure/restart traces, source-contract checks, pinned render evidence, and actual context → container → component → Code / Level up / deep-link / pinned-source verification in work closeout; a render alone is insufficient. No delivery chronology belongs in DESIGN.md. Do not add a scheduler, recovery ledger, provider launcher, approval bypass, or new review for an already-open original review. No software installation or deployment is authorized.

## Data structures

Extend the existing `feature_repair` action in `executions.json`; do not create a repair store. Its stable action ID derives from Feature ID and request ID. Persist the exact request-content digest and origin (direct parent or authenticated human), scoped reason/evidence, accountable Feature, original review URL/forge/review identity/source and target refs, observed source and target heads, review and repair generations, approval and scope references, current owner/claim and existing incident/provider/validation budget identities. Retain the original request and every generation for replay and audit. The immutable review generation remains in `.cascade/reviews.json`; queue cursor and graph checkpoint remain the wakeup state. A reserved child stores Task ID, rendered-spec digest and mint request digest before Task or parent writes.

A typed projection identifies the selected operation, action ID and generation, requested/admitted, acknowledged, executing/executed, waiting/refused, verification pending/verified, evidence and a specific next prerequisite. Admission and queued delivery are distinct receipts. The projection must never infer verification from a Feature status or a queued message.

## API contracts

- `feature_repair` (and a narrow request adapter if needed) accepts an exact request identity and review observation without a Task mismatch. It checks direct-parent authority or an authenticated human mutation context, then rechecks the canonical Feature, original open review, approval/scope, governing comments, dependencies, cancellation, owner worktree/branch, heads, live lease, claim and finite budget under existing lifecycle/owner fences. Missing or stale evidence returns a typed prerequisite. A scoped review response can proceed while its own fix request remains unresolved; unrelated governing comments still gate.
- `supervise_child` and `recover_feature` select that same adapter for an open review and return the typed result. A live graph owner joins or defers. Existing accepted/merged-review follow-up and completed-parent Task-mismatch recovery remain distinct compatible routes.
- A successful admission persists before `FeatureRepairAuthorized` or other stable wakeup is enqueued. Replay after any boundary reuses the action ID, generation, event and reserved child. The Feature scoped `mint_task` path and guarded dispatch, validation and publication use the admitted request and refresh the original review on its current branch.
- `repair_event_authorizes` and independent Watchdog postcheck bind the exact current action, owner, active-path introduction, review generation, corrected source/head, required-check evidence and intended Epic target integration. Missing policy/check/forge evidence is verification pending. The later review-health feature owns cross-forge check normalization; this feature consumes authoritative evidence and fails closed while it is unavailable.

## Logic flow

```mermaid
sequenceDiagram
    participant Caller as Parent or authenticated human
    participant Repair as Feature repair adapter
    participant Ledger as Existing action/review stores
    participant Queue as Queue and checkpoint
    participant Team as Retained Feature team
    participant Watchdog as Independent postcheck
    Caller->>Repair: Exact request and observed original review
    Repair->>Ledger: Recheck gates; persist scoped generation and claim/budget binding
    Repair-->>Caller: Action/generation and admission or typed prerequisite
    Repair->>Queue: Stable authorized wakeup after admission
    Queue->>Team: One owner turn; replay cursor on restart
    Team->>Ledger: Reserve one child, deliver and publish to same review
    Watchdog->>Ledger: Re-read exact action, current checks, review and target proof
    Watchdog-->>Caller: Verified or verification pending with prerequisite
```

On restart the adapter reconciles the action receipt before appending the queue event, the queue cursor before another turn, and the child reservation before allocating a Task. A stale request never edits the current generation.

## Diagram impact and design handoff

| Level and view key | Owner and source symbols | Required change and verification |
|---|---|---|
| Landscape `cascade-landscape`, context `cascade-context` | Root `DESIGN.md`; operator, forge, Cascade | No new actor or external dependency is introduced by the planned adapter. Check the final diff against that boundary and verify navigation into containers. |
| Containers `cascade-containers` | Root and `cascade/DESIGN.md`; supervisor, repository artifacts, War Room | Existing action/review stores, queue and checkpoints retain state. Check the final diff for a new runtime/store and verify persistence links and intended-target boundary. |
| Components `cascade-supervisor-components`, `cascade-team-components` | `cascade/feature/DESIGN.md`, `cascade/epic/DESIGN.md`, `cascade/watchdog/DESIGN.md`, affected Workspace/Task/package designs | Reconcile admission, parent request, queue, guarded Task/publication and independent postcheck collaborators. Update model/contract when the implementation changes relationships; verify both interface sides. |
| Code `cascade-feature-code` | Feature `feature_repair`, `reserve_repair_child`, `mint_task`, registry and new request helpers | Tasks 001 and 003 update source-linked nodes, declaration kinds, replay/claim relationships and Feature normal/failure diagrams. |
| Code `cascade-epic-code` and affected `cascade-workspace-code` | `recover_feature`, `supervise_child`, queue/kickoff symbols | Task 002 updates the parent and wakeup path, source links and restart sequence. |
| Code `cascade-watchdog-code` | `repair_event_authorizes`, postcheck and existing budget/claim symbols | Tasks 001 and 004 update authority and exact-generation verification links, including stale/missing evidence flow. |
| Code `cascade-task-code`, `cascade-teams-code` | Task reservation, validation/provider budgets and publication symbols | Task 003 changes these views and owning designs only where the source contract changes; otherwise records the source-backed no-change reason. |
| Supplementary flow | Feature, Epic and Watchdog designs; affected Workspace/Task designs | Each owner documents inputs, outputs, persistent state and one normal plus one refusal/restart trace against source. |

For every changed Code node, update `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl`, `views.dsl` and `workspace.contract.json` together with the owning `DESIGN.md`. Use real source paths/symbols, declaration kinds and `cascade.codeComponent`/`cascade.parent` metadata. Verify source-contract validation, supported revision-pinned render, context → container → component → Code exploration, Level up, deep-link restoration, pinned-source opening and warm artifact reuse. Preserve renderer bounds and accepted snapshots; record actual checks and gaps in each Task closeout.

## Task breakdown

- `task_051_002_001` — Core durable open-review admission, request fingerprint, gates and replay.
- `task_051_002_002` (after 001) — Direct-parent and authenticated human adapter, typed result and durable wakeup.
- `task_051_002_003` (after 002) — Guarded repair child, dispatch/validation and same-review publication.
- `task_051_002_004` (after 003) — Independent exact-generation postcheck and retirement evidence.

## Planning design review

Reviewed `DESIGN.md`, `cascade/DESIGN.md`, `cascade/feature/DESIGN.md`, `cascade/epic/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/task/DESIGN.md` and `cascade/workspace/DESIGN.md` against the current repair, parent-supervision, queue, reservation and postcheck source. Checked that the named C4 view keys and architecture source/contract files exist and that the existing repair, reservation, parent and postcheck symbols are represented. No DESIGN or C4 source was edited in this planning turn: those documents describe the current mismatch-based repair path, while the open-review admission behavior is still proposed. Tasks 001–004 own source-linked design reconciliation as their implementations land. The required render, interactive navigation, pinned-source opening, normal/failure traces and warm-artifact measurement remain delivery checks; no such result is claimed here.

## Risks & upward questions

Required-check normalization and review-health observation belong to the subsequent review-health Feature. This Feature must report missing or unknown current policy/check evidence as verification pending, with a specific prerequisite; it cannot treat mergeability as green CI. No software installation or deployment is authorized.

## Decision log

- `dec_001` · 2026-11-26 · Feature Lead · **Review repair admission**
  Chose Extend the existing Feature repair action and ledger for direct-parent and authenticated human requests against the original open review; persist admission before wakeup and replay one generation..
  Rationale: The current adapter requires a Task lifecycle mismatch, while an open red Feature review can need repair without one. One action identity preserves scope, owner, claim, budget, review and child reservation across restart.
  Honors: epic_051 acceptance criteria 3–4; REQ-FEATURE-REPAIR-001/002 and REQ-REVIEW-REPAIR-001/002.

- `dec_002` · 2026-11-26 · Feature Lead · **Task sequence and check evidence**
  Chose Implement ledger admission, request routing, guarded child/publication and independent postcheck as four sequential Tasks; treat unavailable current required-check policy or results as verification pending..
  Rationale: Each Task has one durable boundary and focused verification. The subsequent review-health Feature owns cross-forge check normalization, so this Feature must not infer green CI from mergeability or duplicate that normalization.
  Honors: epic_051 feature boundary; current Watchdog postcheck and review contracts.

## Closeout

Completed child work: `task_051_002_001` (Admit scoped open review repairs in the existing Feature action ledger), `task_051_002_002` (Route parent and human fix requests through one durable wakeup adapter), `task_051_002_003` (Execute one guarded repair Task and refresh the original review), `task_051_002_004` (Verify exact review repair generation before closeout).
