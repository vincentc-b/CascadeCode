---
id: feat_049_001
title: Project evidence-based recovery progress
tier: feature
status: completed
parent: epic_049
children:
- task_049_001_001
- task_049_001_002
- task_049_001_003
- task_049_001_004
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 032809336f3fcf3810c7270c28195da9c85a3bf6
created: '2026-11-25'
updated: '2026-11-25'
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
approved_at: '2026-11-25T17:48:03.696221+00:00'
---
# Project evidence-based recovery progress

## Parent Epic

epic_049

## Scope

Deliver the shared recovery progress contract in epic_049, success criteria 1, 2, 4 and the producer/read boundary in 6. This feature owns canonical presentation state, not repair policy.

Required Task acceptance:
- Freeze a versioned safe entry with action/incident/generation/owner/attempt/claim identity, occurrence and observation times, review target, next prerequisite/owner, verification reference, provenance and freshness.
- Distinguish queued, acknowledged, live investigating, live executing, waiting/blocked, failed/exhausted, verification pending, verified completion and stale/unavailable. Match action + generation + attempt evidence. mutation_ready, enqueue, successful attempt and publication do not prove execution or verified resolution.
- Use existing action/incident/stage/postcheck sources and producer lifecycle. Publish a work-ID-addressable bounded current projection outside GET with direct committed-source notification for meaningful transitions; do not rebuild all retained audit history per event or add a scheduler/ledger/paid turn. The selected storage and producer protocol is fixed in the parent Epic.
- Expose concurrent incidents with deterministic primary ordering and continuation. Keep board recovery_incident compatibility and provide additive identity/version metadata for the room. Never hide a newer blocker behind completed or older history.
- Bind live owner evidence to worker/process generation, validity and observation time. Expired, dead, inaccessible and legacy owners cannot claim execution. GET consumes published evidence only; no process/Git/provider probes, raw recovery scans, writes or checkpoint opening.
- Integration tests cover all states, stale/mismatched generation, conflicting evidence, concurrent actions and no read side effects. Use existing local manifest dependencies; install nothing.

Design ownership: War Room owns new progress requirements and safe public contract; Task owns source transitions; Watchdog owns producer freshness/postcheck; Workspace owns worker routing. Carry the epic diagram inventory into Tasks: cascade-dashboard-code, cascade-task-code, cascade-watchdog-code, affected cascade-workspace-code/cascade-teams-code and component ancestors. Add actual source symbols and native declaration kinds, keep model.dsl/views.dsl/workspace.contract.json synchronized, reconcile DESIGN.md without delivery history, and verify normal plus dead-owner/restart flows, context-to-Code navigation and pinned source opening. No invented future symbols in current designs.

Preserve Codex; feature_lead/feature_architect gpt-6-sol high and SWE gpt-5.6-sol medium. No child dispatch before normal plan approval. Return precise contract/API and tests for the dependent transcript/UI features.

Architecture contract resolved by Epic decisions dec_004–dec_006. Required Task acceptance additionally implements the Epic's Selected storage and execution contract: product-root work-addressed immutable pages and writer-only derived index; receipts retained in the authoritative source commit; after-lock notifications and pre-executor start publication; early bounded watchdog drain with startup replay; explicit invocation/executor tokens instead of the queue-aware graph_turn_owner_is_live boolean; 30-second maximum observation validity capped by claim expiry. Measure baseline monolithic ledger cost and publish lag/completeness. Own source durability now so the dependent transcript feature can replay missed transitions without recovering overwritten mutable fields. Freeze receipt/API identity with Feature 2 before delivery. Carry the precise crash/identity and Code-navigation cases into Tasks.

## Data structures

- **Authoritative transition receipt v1:** retained in the same action/incident commit as the material state change, with canonical source kind/key, action ID, original incident ID if known, authoritative generation, owning graph and affected work IDs, attempt/claim IDs when present, monotonic per-source transition sequence, nullable source occurrence time, allowlisted transition kind/stage and safe reference. Its deterministic `receipt_id` hashes those identity fields, not message text, clock refresh or observation time. Repeated stage entries with distinct source sequences remain distinct. Receipts are observational and never grant repair authority. Retain them until a future transcript consumer durably acknowledges delivery.
- **Progress entry v1:** stable `entry_id` for action + generation + attempt; `action_id`, `original_incident_id?`, `generation`, `graph_id`, `affected_work_id`, `owner`, `attempt_number?`, `claim_id?`, `state`, `stage?`, `occurred_at?`, `observed_at`, `valid_until?`, `freshness`, `provenance`, `safe_reason`, `prerequisite?`, `next_step`, allowlisted `target?`, `verification_ref?`, and ordered `receipt_refs`/`milestone_refs`. A missing source time stays null. Milestone refs are pending until Feature 2 commits the matching transcript event.
- **Current projection v1:** product-root `.cascade/recovery_progress/v1/work/<sha256(work-id)>/current.json` points to an immutable revision manifest and bounded pages. The manifest embeds the exact work ID, product/tracking identity, schema, revision, producer runtime identity, observed/expiry times, completeness, lag and continuation. Owning graph and affected-work aliases carry the same entry identity/revision. A writer-only disposable SQLite index tracks current entries, source receipts, dirty identities and fair drain cursors; action/incident stores remain authoritative.
- **Live observation v1:** invocation begin/end and executor entry/exit tokens bind worker runtime generation, PID/boot/process-start identity, graph, action generation, attempt/claim and observation time. Only matching registered live tokens may be refreshed. Validity is at most 30 seconds and ends sooner at claim expiry; death/stop invalidates it immediately when observed. Unknown/inaccessible process identity is unknown, not live.

## API contracts

- `GET /api/recovery/progress?work_id=<id>&cursor=<opaque>` reads a single work-addressed published projection. A successful versioned envelope returns `schema_version: 1`, exact `work_id`, `revision`, `observed_at`, `expires_at`, `completeness` (`complete|incomplete|pending`), `lag` (backlog count/oldest pending when known), `primary`, ordered `items`, and `next_cursor`. Default page is 50, maximum 100 entries. Cursor binds work ID, revision and sort position; mismatched input is 400 and a superseded revision returns a typed 409 restart with current revision. Missing, corrupt, incompatible, stale or wrong-root evidence returns explicit pending/unavailable metadata, never a healthy empty result.
- The board's existing `recovery_incident` remains a compatible primary summary, with additive `recovery_progress` version/revision, entry identity, freshness, count and continuation. The board and room consume the same published reader; a later poll revision cannot silently regress the selected action. Across all requested board work IDs, GET opens only direct pointers, manifest and requested immutable pages using regular-file no-follow opens, at most 100 entries, 1 MiB source bytes and 256 KiB serialized response. It never opens the writer index, raw action/incident ledger, graph checkpoint or full transcript, and never probes Git, provider or process state or writes.
- State derivation uses matching action + authoritative generation + attempt + claim evidence. Requested/queued requires a durable request/routing identity; acknowledged requires a matching timestamped owner acknowledgement; investigating requires a fresh admitted graph invocation and no matching live repair; executing requires a still-open matching attempt, valid claim and fresh executor/process evidence. A recorded prerequisite yields waiting/blocked with responsible owner and safe next step. Durable refusal/failure and budget exhaustion remain distinct. Attempt or publication success without fresh same-generation Watchdog postcheck is verification pending; only the authoritative postcheck makes verified complete. Expired, dead, inaccessible, legacy or conflicting evidence yields stale/unavailable with last supported historical fact. Enqueue, `mutation_ready`, PID existence and successful attempt alone never assert execution or resolution.
- Concurrent entries sort unresolved blockers first, other unresolved next, verified completion last; then newest material occurrence and stable `entry_id`. A stale entry retains the last supported blocker priority. Pagination preserves the remaining entries. Targets and reasons are allowlisted/sanitized; no raw metadata, prompts, reasoning or subprocess output enters the public contract. Freeze receipt and entry identity plus route shape with feat_049_002 before delivery.

## Logic flow

```mermaid
sequenceDiagram
    participant Owner as Task or Watchdog source
    participant Store as Action or incident store
    participant Pub as Supervised progress publisher
    participant Index as Writer index and immutable pages
    participant UI as Board or room GET
    Owner->>Store: Commit material transition and receipt under lifecycle lock
    Store-->>Owner: Committed receipt/snapshot
    Owner->>Pub: Notify after outer lock; start before long executor call
    Pub->>Pub: Join exact generation, claim, live token and postcheck
    Pub->>Index: Update affected aliases and publish bounded revision
    UI->>Index: Read direct pointer, manifest and requested pages
    alt Notification lost or worker restarts
        Pub->>Store: Bounded receipt/owner drain using persisted cursor
        Pub->>Index: Replay identity and publish lag/completeness
    else Owner dead or evidence expires
        Pub->>Index: Publish stale/unavailable, retain historical fact
    end
```

The fast path spends at most 250 ms on one affected batch and leaves lag for retry on fence/disk failure without changing repair admission or outcome. `watchdog_tick` drains early, outside `process_lock` and before slow dispatch; startup schedules the same drain. Each pass handles at most 100 receipts/owners or one second with fair continuation. Legacy import is resumable and marks incomplete coverage until finished. Source ledger load/atomic replacement cost is measured separately; the publisher does not reload the monolithic ledger for every receipt in one batch. No independent scheduler, model turn or new repair ledger is introduced.

## Task breakdown

| Task | Owns | Depends on |
|---|---|---|
| `task_049_001_001` | Committed transition receipts and notifications | — |
| `task_049_001_002` | Generation-bound invocation and executor evidence | `task_049_001_001` |
| `task_049_001_003` | Current materializer, index, immutable pages and drain | `task_049_001_001`, `task_049_001_002` |
| `task_049_001_004` | Bounded API, board compatibility and final verification | `task_049_001_003` |

1. **Retain source transition receipts.** Task-owned action writes and Watchdog stage/result/postcheck writes retain minimal immutable identities in their authoritative commits. Notify after the outer lock; dispatch a committed attempt-start receipt before executor entry and preflight refusals as refusal. Preserve repair policy and source durability across a missed notification.
2. **Record invocation and executor liveness.** Workspace kickoff and Task resume paths emit exact begin/end and entry/exit tokens; supervised refresh binds runtime/process generation, claim validity and observation time. Queue-aware `graph_turn_owner_is_live` is not execution proof. Exercise dead, inaccessible, expired, mismatched and restart cases.
3. **Materialize bounded current progress.** Implement the single safe state machine, deterministic concurrent ordering, writer-only derived index, immutable work pages, after-lock fast path and bounded Watchdog/startup drain. Preserve alias identity/revision, lag, legacy provenance and same-generation postcheck authority; measure monolithic source cost and publication lag/completeness.
4. **Expose the shared read contract and verify delivery.** Add direct bounded GET and board compatibility using only published pages; freeze receipt/API identity with feat_049_002. Cover all states, competing/mismatched evidence, concurrent actions, read side effects, crash between source commit and notification, held long executor, restart, split roots, stale cursors and budget exhaustion. Reconcile affected designs and native C4 Code views against final source and verify context-to-Code, Level up, deep link and pinned source opening.

**Diagram-impact inventory and ownership.** Architecture source is `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`; changes to these three remain synchronized. Landscape/`cascade-context`: Task 4 verifies the existing operator/system/external boundaries; no new external actor is planned. `cascade-containers`: Tasks 3–4 verify War Room/supervisor/repository read-write relationships without implying a new deployed service. `cascade-supervisor-components` and `cascade-team-components`: Tasks 1–3 update receipt, producer and invocation handoffs. `cascade-war-room-components`/`cascade-dashboard-code`: Tasks 3–4 update source-linked projection/reader nodes. `cascade-task-code`: Task 1 updates `create_or_load_action`, `acknowledge_team_recovery`, `_claim_resume_attempt`, `record_action_checkpoint`, `finalize_attempt`, `resume_action`; Task 2 updates actual executor-token symbols. `cascade-watchdog-code`: Tasks 1 and 3 update actual `incident_record`, `recovery_stage_receipt`, result/postcheck and drain symbols. `cascade-workspace-code` and affected `cascade-teams-code`: Task 2 updates kickoff observation and Task 4 verifies routing/publication ownership. Supplementary flows: Task/Watchdog/Workspace owning designs explain normal, dead-owner and restart paths; War Room design owns public state/read contract. Each changed native custom Code view uses actual `cascade.codeComponent`, `cascade.parent`, `cascade.sourcePath`, `cascade.sourceSymbol` and declaration kind. Task 4 validates source contract, local render, pinned source links, navigation/deep-link restoration, warm artifact reuse and render bounds; it records measured results and no-change reasons per level.

**Design review at planning:** Reviewed `DESIGN.md`, `cascade/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md` and `cascade/workspace/DESIGN.md` against current source and the pinned model/views. Existing designs describe coarse routing summaries, full chat reads, action claim boundaries and independent postcheck as current facts. Proposed progress symbols and persistence are kept in this work record until implementation. No current-design edit is warranted before source changes; implementation tasks own reconciliation and the final diff review.

## Risks & upward questions

The monolithic source ledger's load and atomic replacement remain unbounded in source size; report measured baseline and publication lag rather than claiming byte-bounded writes. A process that becomes inaccessible cannot establish execution; report unavailable until authoritative observation returns. Feature 2 must consume retained receipt identities and agree on the safe public entry contract before Feature 1 delivery.

## Decision log

- `dec_001` · 2026-11-25 · Feature Lead · **API contracts**
  Chose Use one versioned work-addressed current progress envelope with direct immutable-page reads, stable receipt/entry identity, deterministic primary ordering and explicit pending/restart semantics.
  Rationale: A shared projection keeps board and room consistent, preserves concurrent blockers and gives the transcript feature durable source identities without inferring state on GET.
  Honors: Epic dec_004–dec_006, success criteria 1, 2, 4 and 6; source authority, bounded read and no repair side effects.

- `dec_007` · 2026-11-25 · Feature Lead · **Task breakdown**
  Chose Sequence source receipts and exact live evidence before the materializer, then integrate the public reader and architecture verification.
  Rationale: The publisher must consume committed transition identities and generation-bound liveness; the public API can then be tested against actual published pages and handed to dependent features.
  Honors: Selected Epic storage/execution contract, no child dispatch before plan approval, design implementation-depth and frugal testing.

## Closeout

Completed child work: `task_049_001_001` (Retain committed recovery transition receipts), `task_049_001_002` (Record generation-bound live invocation and executor evidence), `task_049_001_003` (Publish bounded evidence-based current recovery progress), `task_049_001_004` (Expose bounded recovery progress reads and verify shared contract).
