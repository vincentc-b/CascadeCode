---
id: epic_049
title: Expose recovery progress and durable team transcript milestones
tier: epic
status: active
parent: null
children:
- feat_049_001
- feat_049_002
- feat_049_003
- feat_049_004
- feat_049_005
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-14'
updated: '2026-11-26'
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
# Expose recovery progress and durable team transcript milestones

## Intent

Let an operator see whether recovery has only been requested, has been acknowledged, is actively executing, is waiting on a prerequisite, or has finished. Show this on the War Room board and the owning team's Historical transcript without requiring inspection of runtime JSON or inference from old team summaries.

Observed on 2026-11-14: epic_044's implementation review, https://github.com/vincentc-b/CascadeCode/pull/243, conflicted with main. Recovery action resolution:v1:8bacbfcc9a7211006229507469fdc5acee119cee28d8e41dc0a356cdb60a1404 was queued at 03:58:01 UTC, acknowledged at 03:58:10, and claimed as running at 04:02:25. The board continued to say Recovery investigating because its projection keys off routing_marker.status == enqueued. The Historical transcript still ended at 03:41 with an older no-recovery-needed summary. The running attempt was visible only in the durable action ledger.

Current code mirrors role responses into chat after graph invocation returns; it does not expose live recovery milestones. A queued handoff, a live owner turn, a claimed repair attempt and verified resolution are distinct facts. Historical assertions must remain dated history rather than appear to describe current health.

### Success criteria

1. Project current recovery progress from existing durable action, handoff, attempt and claim evidence. Distinguish requested/queued, acknowledged, executing, waiting/blocked, failed/exhausted and verified completion where supported. Show the owner, action/review link, last transition time, attempt number and next safe step. A routing marker alone must never claim active execution; admission marked mutation_ready is authorization, not proof of a mutation.
2. Make running status truthful: require valid execution/owner evidence, handle expired claims and dead workers, and distinguish a live investigating team turn from an executing repair attempt. Report stale or unavailable evidence explicitly. Waiting states explain the actual prerequisite and responsible owner; do not infer a human gate from elapsed time alone.
3. Append safe, concise, durable system milestones to the owning team's Historical transcript as transitions occur, without waiting for the entire manager/architect turn to finish. Include queued, acknowledged, attempt started, meaningful stage changes when durably available, waiting/failure, publication and verified completion. Identify the recovery action and review and use event occurrence times. Keep final manager/architect summaries and clearly distinguish system recovery events from authored role messages.
4. Keep a current recovery summary visible beside the Historical transcript and on the board. Both views must agree on action identity and state; preserve or link concurrent incidents without silently hiding a newer blocker. A historical no-recovery-needed message must not override current evidence. Link current recovery to relevant transcript milestones and the review.
5. Survive refresh, navigation and worker/service restart. Coalesce repeated observations; one material transition produces one milestone despite repeated polling, duplicate delivery or concurrent workers. Preserve attempt/generation identity and order, avoid duplicate final role summaries, and reconcile missed milestones from durable evidence with provenance. Legacy records lacking timestamps must be labeled honestly rather than assigned fabricated historical times.
6. Keep UI reads bounded and read-only. Reuse existing projections and durable stores; do not trigger recovery, Git/provider probes, full-history scans or writes from GET/poll paths. Progress updates must not depend on model-generated commentary and must not create extra paid agent turns. Define bounded history/pagination behavior using the existing transcript conventions.
7. Add meaningful API and browser regressions for queued-but-idle recovery, acknowledgement, a long-running turn with a live repair attempt, waiting for checks or publication, dead/expired owner evidence, failure/retry, changed generations and independently verified completion. Exercise repeated refresh, concurrent delivery and restart; prove no duplicate milestones, no invented progress and no repair side effects from reads.
8. Reproduce the epic_044 timeline in a deterministic fixture and validate the operational UI through supported entry points. During a long-running recovery, the board and current summary must show the supported live state, and the transcript must display its start milestone before the role's final reply. Document remaining limits instead of claiming live tool-output streaming or successful recovery from a claimed attempt alone.

## Macro-architecture

### Scope and baseline

This is a visibility change inside the current supervisor and War Room. It adds no scheduler, repair authority, recovery ledger, provider invocation, or tool-output streaming. It does not make a queued request, admission, publication, successful attempt, or stale claim equivalent to independently verified resolution.

Repository assessment:

- `cascade/war_room/recovery_incident.py::recovery_incident_from_action` exposes failed/investigating/blocked from routing and blocker evidence; `recovery_incidents_by_work_id` retains one non-completed action per affected row. It does not distinguish acknowledgement, valid live execution, concurrent actions or verified outcomes.
- `cascade/task/action_recovery.py` owns persisted actions/attempts, `acknowledge_team_recovery`, `_claim_resume_attempt`, `finalize_attempt`, `record_action_checkpoint`, and generation envelopes. Review-publication claims additionally retain process identity. `cascade/watchdog/incidents.py` supplies generation identities, claim expiry and durable stage receipts; these are evidence to consume, not new execution policy to invent.
- `cascade/workspace/kickoff.py::graph_turn_owner_is_live` is process-local owner evidence. A graph checkpoint or pending queue alone cannot identify an executing repair. A producer must bind any live observation to its worker/process generation and observation time.
- `planning_transcript.py::append_planning_turn_to_chat` runs after graph return. Its backfill deduplicates role/body pairs; `chat_store.py::append_transcript_message` generates a fresh UUID and append time and uses an in-process lock. Neither supplies cross-process event deduplication or historical event timestamps.
- `sidecar_routes.py::handle_get_chat` is already read-only, but `read_messages` reads the full JSONL file. Audit pages already have bounded immutable projections and explicit freshness. Preserve those boundaries and extend the current producer/consumer conventions.

Accepted-code overlap: current `audit_projection.py`, `audit_projection_reader.py`, `incidents.py`, `incident_postcheck.py`, and publication recovery provide the health-audit and recovery-evidence foundations relevant to epic_044 and epic_048. Requests for those epics' historical work/Git evidence were refused as outside this team's scope. Their delivery records and exact accepted review ancestry have therefore not been verified in this turn. Do not bypass that refusal. Architect review must use permitted evidence or record the specific remaining provenance limitation. No new dependency on either broad workstream is justified by the currently available code.

### Shared public progress contract

One versioned, safe projection feeds board rows, the owning-room current summary and milestone serialization. Feature 1 owns this contract; later features consume it without reimplementing state inference.

Every entry carries stable action ID, original incident ID where available, authoritative generation, owning graph/work identity, affected work identity, review/action target, attempt number and claim identity where present, state and optional durable stage, source occurrence time (nullable), observation/freshness evidence, safe reason, responsible prerequisite owner, next safe step, and milestone references. Unknown legacy values remain explicit. Review URLs and text are validated/allowlisted; raw metadata, prompts, private reasoning and subprocess output never reach these fields.

| Display state | Required evidence and guard |
|---|---|
| Requested / queued | Durable recovery request and routing identity. No assertion that a team is live. |
| Acknowledged | Matching action/owner acknowledgement with recorded time; does not prove current liveness. |
| Investigating | Fresh, generation-bound live owner-turn evidence; no matching live repair attempt. |
| Executing | Open matching attempt plus valid claim and fresh owner/process evidence for that attempt and generation. A queued turn or `mutation_ready` admission is insufficient. |
| Waiting / blocked | Concrete recorded prerequisite, responsible owner and safe next action. Only an explicit human gate is labeled human action required. |
| Failed / exhausted | Durable failure/refusal or exhausted bound; retain attempt identity and distinguish retryable failure from exhausted allowance. |
| Verification pending | Attempt/publication succeeded but an authoritative same-generation postcheck has not confirmed resolution. |
| Verified complete | Fresh authoritative same-generation verification reference confirms the obligation. A stale result for an older generation cannot clear a current incident. |
| Stale / unavailable | Required evidence is expired, incomplete, inaccessible, corrupt or belongs to another worker/generation. Preserve the last supported historical fact and its timestamp without claiming current execution or health. |

These are evidence projections, not mandatory sequential workflow states. Retries create new attempt identity; new material generations remain distinct. Stage labels such as validating, publishing and verifying appear only with matching durable receipts. A proven-dead owner invalidates executing; inaccessible ownership is unknown. Elapsed time alone never invents a human gate.

Return a bounded ordered list of concurrent incidents plus a deterministic primary item: unresolved blockers first, then other unresolved items, with newest material occurrence and stable identity as tie-breakers. Completed history cannot hide newer unresolved work. Pagination/continuation preserves all remaining incidents. The existing `recovery_incident` board field remains a compatible primary summary while additive versioned data provides identity, detail and concurrency. Board and room identify the same projection revision; temporarily different poll revisions show freshness and cannot silently regress the selected action.

### Persistence, notifications and recovery

Existing action/incident stores remain authoritative. Material transitions notify a deterministic non-model publisher after the authoritative write commits. Use the existing supervisor/audit producer lifecycle for bounded reconciliation and stale-owner refresh; do not wait for the role's final response or add a paid turn. The selected storage, notification and replay protocol below is part of the Feature contracts and must be copied into the owning Task acceptance criteria.

The milestone append path uses the owning graph's existing transcript storage, with additive event metadata and a deterministic event key bound to source record/receipt, action, generation, attempt and material transition identity. Repeated polling or a changed observation timestamp cannot mint an event. Repeated entry into the same stage within an attempt must remain distinguishable when the source records distinct material transitions.

The graph-scoped OS file lock, durable append intent and derived offset/event index specified below protect durable event uniqueness. Do not claim that `process_lock` alone is a multiprocess fence. Record source occurrence time separately from append/reconciliation observation time and provenance. Legacy records without reliable time say “time unavailable”; never backdate them to a fabricated timestamp. Keep final authored messages intact and give checkpoint-origin role summaries a stable identity that deduplicates direct append and restart backfill without suppressing separate identical replies.

The source commit and chat append need not be one transaction: a crash after source commit is recovered from durable source identity; a crash after chat append but before cursor advancement must not duplicate it. Reconciliation runs on the writer/supervisor path, is bounded and resumable, and handles graph routing across feature dispatch, team completion and split product/tracking roots. A transcript failure must not lose or alter recovery evidence or block/authorize a repair. Expose projection lag/unavailability and retry through the existing supervised lifecycle.

```mermaid
sequenceDiagram
    participant Recovery as Existing recovery owner
    participant Store as Action and incident stores
    participant Publisher as Deterministic progress publisher
    participant Chat as Owning graph transcript
    participant UI as Board and Historical view
    Recovery->>Store: Commit request, acknowledgement, attempt or receipt
    Store-->>Publisher: Notify committed source identity
    Publisher->>Publisher: Derive safe state and idempotent transition key
    Publisher->>Chat: Append missing system milestone under durable fence
    Publisher->>Publisher: Publish bounded current projection
    UI->>Publisher: Read current projection only
    UI->>Chat: Read bounded transcript page only
    Note over Recovery,UI: Attempt-start milestone is observable while role turn is still running
    alt Restart or missed notification
        Publisher->>Store: Bounded cursor-based reconciliation outside GET
        Publisher->>Chat: Replay same event key; append only if absent
    end
```

### Selected storage and execution contract (proposal)

These are implementation decisions, not claims about the current runtime. Feature 1 owns progress materialization and source evidence; Feature 2 owns transcript persistence and replay; Feature 3 owns presentation and operational acceptance.

**Progress layout.** Keep recovery authority in the existing action/incident stores. Publish derived immutable work-addressed pages beneath the canonical product root `.cascade/recovery_progress/v1/`: `work/<sha256(work-id)>/current.json` points to an immutable revision manifest and bounded current pages. The manifest embeds exact work ID, product/tracking identity, schema version, revision, producer runtime identity, observed/expiry times and completion/lag status. Validate the embedded identity rather than trusting the path hash. Both owning graph and affected work aliases refer to the same entry identity and material revision. A writer-only stdlib SQLite index at this root indexes current entries by graph/work, action, generation and deterministic primary sort key, and tracks imported source receipts. It is disposable derived data, not a repair ledger or authorization source. Update only affected work pages; do not rebuild the health-audit epoch per transition. Reuse audit reader's no-follow regular-file, immutable-page and restart conventions, without mixing the two epoch namespaces. GET opens only the direct work pointer, manifest and requested pages, with the same aggregate 100-row / 1 MiB source / 256 KiB response ceilings, including multiple board work IDs. Return explicit incomplete/pending and continuation on exhaustion. No directory-wide history scan or SQLite initialization on a read.

**Source durability and ordering.** At material authoritative writes, retain a minimal immutable transition receipt in that same action/incident commit, under its existing lifecycle lock. Reuse an existing immutable receipt when sufficient; add a monotonic per-source transition sequence where mutable routing/checkpoint fields otherwise overwrite history. Receipt identity comprises canonical source kind/key, action, original incident when known, authoritative generation, attempt/claim and transition sequence. It includes nullable occurrence time, owning graph and an allowlisted payload. It is observational evidence and cannot grant a recovery capability. Occurrence-time equality, body equality and observation refresh are never identities. Retain receipts until their transcript delivery is durably acknowledged; no automatic pruning of source evidence is authorized. The existing monolithic ledger's load/atomic replacement cost remains an explicit baseline cost; no claim of byte-bounded source mutation is made. Publisher batches bound additional projection/replay work, and must not perform another whole-ledger load for each transition.

**Notification and scheduling.** Task `create_or_load_action`/routing updates, `acknowledge_team_recovery`, `_claim_resume_attempt`, `record_action_checkpoint`, `finalize_attempt`, and Watchdog persisted stage/result/postcheck writes notify the deterministic producer with the committed receipt/snapshot after the outer lifecycle lock releases. In `resume_action`, dispatch the committed start receipt after claim/preflight and before the executor's potentially long call. Preflight refusal yields its own outcome, never an executing claim. The best-effort fast path publishes one affected batch with a 250 ms lock/work budget; disk or fence failure records lag and leaves durable receipts for retry, without changing repair admission or outcome. `watchdog_tick` runs a bounded drain early, outside `process_lock` and before potentially slow network/dispatch work; worker startup schedules the same drain. The existing supervisor supplies repeated opportunities even when periodic health audits or automation are disabled. No model turn, independent timer/service or wait for `_invoke_role_turn` completion is added. Drain at most 100 receipts/owners or one second per pass; persist fair continuation, expose backlog/oldest pending evidence, and yield rather than hold lifecycle locks while touching chat. Startup source discovery can reuse the existing supervisor source snapshot; subsequent drains use dirty identities and stored cursors. Legacy import is resumable and reports incomplete coverage until finished.

**Live evidence.** Add explicit begin/end invocation observations around the admitted graph invocation in `kickoff.py`, and executor entry/exit observations around `resume_action`, bound to worker runtime generation, PID/start identity, invocation token, action generation and attempt claim. The supervisor refreshes only matching registered live tokens; a process being alive or a queue having unfinished work is insufficient. The producer joins those observations to a still-open canonical attempt and valid claim. Use a 30-second observation validity ceiling, capped by any earlier claim expiry; expose stale when refresh is unavailable. These observations are derived liveness only and cannot reclaim a claim. `graph_turn_owner_is_live` currently returns true for unfinished queue work as well as a held graph lock; its boolean must not be reused as executing proof. Unknown ownership stays unknown; a recorded stop/death invalidates executing immediately when observed. Watchdog retains sole ownership of fresh same-generation postcheck truth.

**Transcript fence and index.** Retain each room's existing JSONL as the authoritative message history. Use a graph-scoped advisory OS file lock in the canonical tracking runtime root (stable across worktree routing), in addition to thread serialization. All append, explicit sync and human-ingest rollback writers must cooperate. A writer-only SQLite index under tracking `.cascade/transcript_index/<graph-hash>.sqlite` stores unique event/message keys, append sequence, JSONL byte offsets/lengths, file incarnation, indexed end offset and one pending append intent. Its rows are derived except the pending intent, which is a write-ahead copy of the exact intended safe line and source key. Under the graph fence: resolve the current room and incarnation; reconcile pending intent; commit intent with expected tail offset and line digest; append the complete line and fsync JSONL; then transactionally mark its unique key/offset committed and clear intent. Only then acknowledge the source receipt. On crash before append, replay the intent; after complete append but before index commit, verify that exact tail and commit without appending; repair only a provably matching partial intended tail. Unexpected bytes or routing ambiguity fail pending without truncating unrelated history. Sync index/intent storage durably. Never acquire a source lifecycle lock while holding the graph fence: take source snapshots first and acknowledge only after releasing the fence. Projection publication remains independent of transcript availability and labels pending milestone references until append is committed.

**Read pages and legacy history.** Publish immutable bounded transcript page sidecars under the tracking runtime index root from committed offsets, with a direct graph pointer and incarnation. UI GET reads these page sidecars, never the writer index or unbounded JSONL. Incremental cursors bind graph, incarnation and committed append sequence; backward pages retain a snapshot high-water mark, forward refresh advances monotonically, and ordinary append does not invalidate older pages. A rollback/rewrite or room move changes incarnation and gives a typed restart. Default 50/max 100 rows, 1 MiB source and 256 KiB serialized response apply across pointer/manifest/pages. Oversize legacy messages receive a bounded preview with explicit truncation/provenance and a bounded chunk-detail continuation; no history is deleted or silently skipped. Legacy import runs in 1 MiB/100-row chunks with stored byte offsets, retains original UUID/append time, and leaves occurrence time null. Missing/corrupt/unbuilt index is pending; GET does not build it. The legacy `/api/chat/<graph>` array returns the bounded latest window with `Link` continuation and explicit completeness/incarnation headers; unavailable history returns a typed error rather than an empty healthy array. The versioned envelope adds items, older/after cursors, high-water mark, freshness and completeness. Feature 2 fixes concrete route/query/header names in its plan and contract tests before Feature 3 dispatch.

**Authored reply identity and routing.** Carry graph checkpoint lineage plus persisted message ordinal (or an existing durable message ID) through direct append and backfill. Ordinary checkpoint revisions must not change identity for an existing message; a reset/fork starts a new lineage. Distinct identical replies retain distinct keys. Legacy author/body matches can conservatively suppress ambiguous replay only with explicit legacy provenance; they cannot claim exact deduplication. Owning graph routing uses the existing registered tracking document owner, never a raw action-provided path. Dispatch, completion and split-root room movement hold the stable graph fence, copy committed history, reconcile pending intent and rebuild/rebind derived pages before switching incarnation. Until routing can be proved, keep pending delivery at the source and current projection visible; never append to a stale checkout. Task-origin milestones route to the accountable persistent Epic/Feature team, preserving the Task as affected identity.

**Crash acceptance matrix.** Owning tasks must inject failures after source commit/before notification, after intent commit/before append, during partial append, after fsync/before index commit, after index commit/before source acknowledgement, and during room movement. Race two real OS writer processes. Require one row per retained receipt, no loss of unrelated JSONL bytes, eventual fair drain, explicit lag and no replayed repair effect. Also prove an ordinary tick and the start fast path remain usable while a role's final response is held. Baseline source-ledger loading and storage exhaustion are measured/reported limits, never silently described as bounded success.

### Read and presentation boundaries

Current summaries stay visible adjacent to Historical and on board rows, including when older authored messages assert no recovery was needed. System milestones have an explicit “System · Recovery” presentation, occurrence-time label, action/review link, attempt/generation detail and a stable anchor. They are operational facts, not attributed manager/architect statements.

Use a versioned transcript page interface with default 50, maximum 100 rows, at most 1 MiB source bytes and 256 KiB serialized response per request. Adapt the browser to explicit cursors, load-older and incremental refresh while retaining scroll position and existing authors/message fields. Preserve the legacy array-shaped chat route with a bounded latest window and explicit continuation metadata (headers or negotiated version), never silent truncation. Cursor identity must bind graph, file/projection generation and position; invalid/stale cursors get a typed restart response, not an empty history. No pruning of legacy transcripts is authorized. Feature 2 freezes the precise API before Feature 3 starts.

GET/poll must not append/backfill, open graph checkpoints, run provider/Git/process probes, trigger repair, scan full transcripts/actions, or schedule model work. Freshness is read from producer evidence and the clock. The browser only renders the server projection. Any existing board recovery scan must move behind a bounded current index; unrelated board lifecycle parsing is outside scope.

### Diagram-impact inventory and requirement ownership

Architecture root: `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/`. Change `model.dsl`, `views.dsl` and `workspace.contract.json` together. Current design facts stay in owning designs; proposed behavior and this inventory remain here until implemented. The Architect owns the planning baseline review; each Feature's tasks must include the corresponding implementation and verification below.

| Level / view key | Owning design and source boundary | Required update / owner / validation |
|---|---|---|
| Landscape and `cascade-context` | `DESIGN.md`; operator, local Cascade, repository and forge | No new person, system or external dependency: keep topology; Architect verifies visibility responsibilities still match scope. |
| `cascade-containers` | `DESIGN.md`, `cascade/DESIGN.md`; War Room, supervisor, repository | Keep runtime boundaries; derived projection and transcript persistence remain repository artifacts. Do not model Python modules as separately deployed services. Architect/F1 verify read/write relationship labels. |
| `cascade-supervisor-components`, `cascade-team-components` | `cascade/DESIGN.md`, Task, Watchdog and Workspace designs | F1/F2 show action evidence, supervised producer, kickoff and transcript handoff responsibility; no new scheduler or execution authority. |
| `cascade-war-room-components`, `cascade-dashboard-code` | `cascade/war_room/DESIGN.md`; `recovery_incident_from_action`, `recovery_incidents_by_work_id`, `handle_get_chat`, `read_messages`, `append_transcript_message`, `append_planning_turn_to_chat`, `sync_planning_transcript_to_chat`, board/chat UI | F1 owns progress projection nodes; F2 owns transcript writer/page nodes; F3 reconciles route/UI nodes and code navigation. Planning baseline adds current recovery projection, chat read/append and direct/backfill nodes; F1/F2 replace the documented coarse/full-read limits with actual implemented nodes and F3 verifies navigation. |
| `cascade-task-code` | `cascade/task/DESIGN.md`; `acknowledge_team_recovery`, `_claim_resume_attempt`, `finalize_attempt`, `record_action_checkpoint`, `resume_action` | F1/F2 show committed transition boundaries, claim/attempt identity and notification ordering without changing repair policy; verify normal claim and interrupted attempt against source. |
| `cascade-watchdog-code` | `cascade/watchdog/DESIGN.md`; `incident_record`, `recovery_stage_receipt`, `publish_audit_projection`, postcheck integration | F1 shows safe evidence projection/freshness and generation verification; F2 shows bounded reconciliation scheduling if wired here. Existing audit pipeline and required new paths must be distinguished. |
| `cascade-workspace-code`, `cascade-teams-code` | `cascade/workspace/DESIGN.md`, `cascade/DESIGN.md`; `graph_turn_owner_is_live`, kickoff transcript calls and review publication | F1/F2 trace live owner observation, role-return/backfill, restart and source-root routing. Preserve component ownership: a symbol has one Code owner; cross-component references link to it. |
| `cascade-architecture-browser-code` | `cascade/war_room/DESIGN.md`; `snapshot_projection`, `_snapshot_projection`, `snapshot_documentation_projection`, browser `remainingViews` | Planning review found the full model exceeded 256 KiB. The owning branch now shrinks view pages under the existing cap and follows continuation for document context. Existing snapshot-projection Code node and browser/API relationship remain accurate; no new runtime boundary or render process. Verify lossless HTTP paging, minimum-page refusal, actual Code/deep links and unchanged render-operation count. |
| Supplementary sequence / state views | War Room owns transcript append/replay; Task owns action transitions; Watchdog owns liveness/postcheck; Workspace owns graph routing | F1/F2 add normal and failure/resume Mermaid diagrams, persistence locations, error behavior and links back to model/view keys. F3 verifies UI ordering, navigation and freshness transitions. |

Existing stable requirement owners: `REQ-WARROOM-001`, `REQ-WARROOM-AUDIT-001/002`, `REQ-WATCHDOG-002/004`, `REQ-WORKSPACE-C4-001/002/003` and `REQ-CASCADE-RECOVERY-002`. New progress and milestone requirements belong in the War Room design under subsystem-scoped IDs; Task/Watchdog/Workspace own only their local write, reconciliation and routing contracts and link back instead of duplicating the presentation requirement.

Every affected Code view uses native custom views with `cascade.codeComponent`; each actual implementation node has `cascade.parent`, source path, source symbol and correct native declaration kind. New proposed functions must not be presented as existing source. Validate contract/source links and pinned rendering; exercise context → containers → component → Code, Level up, deep-link restore and pinned source opening for representative progress and transcript nodes. Include stale/renamed symbols, ownership drift, warm artifact reuse and bounded renderer process counts. Do not rewrite accepted snapshots or bypass revision-pinned publication. Record measured navigation timing, not a universal latency promise.

## Cross-module constraints

Use the normal Epic/Feature/Task planning and review workflow. Activation authorizes planning. Feature implementation remains gated by normal Epic plan approval.

Reuse cascade/war_room/recovery_incident.py, planning_transcript.py, chat_store.py, sidecar_routes.py, board/chat UI, workspace kickoff and existing action recovery/claim/handoff records. Investigate these boundaries before choosing implementation. Do not introduce a parallel recovery scheduler or ledger, change repair authority or bypass review/validation gates. The work is visibility, not a change to recovery execution policy.

Coordinate with epic_044 health audit presentation and epic_048 self recovery evidence/verification requirements; inspect their accepted changes before planning to avoid duplicate work. Do not require waiting for unrelated broad recovery work if existing durable records support this scoped visibility improvement. Any formal dependency must be established during planning.

Preserve transcript/history, stable action identities and raw recovery evidence. Do not expose credentials, provider prompts, private reasoning or unbounded subprocess output. Show only safe operational facts and summaries. Existing human approvals, ownership, leases and exact-generation verification remain authoritative.

Use Codex and retain the explicit role model/reasoning selections for descendants. Do not change workspace-wide settings.

## Core dependencies

Canonical software manifest revision 2 is ready: Python 3.12.8; PyYAML 6.0.3; cursor-sdk 1.0.37; LangGraph 1.2.14; SQLite checkpoint adapter 3.1.1; pytest 9.0.3; Git 2.34.1; Node 20.20.2; Playwright 1.64.0; Chromium 156.0.8078.4; Docker 28.0.0; Structurizr image pinned to `sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c`.

The intended validation target is the existing Linux x86_64 local host `ip-172-31-37-14`, using `/opt/conda/bin/python3.12`. The canonical dependency executor is rooted at `/home/ubuntu/dev/CascadeCode`; owned implementation and tests use `/home/ubuntu/dev/CascadeCode/.cascade/worktrees/epic_epic_049`. These checks prove local tool availability only, not a deployed runtime or another target. Exact identities, installed binary/RECORD hashes and verification commands are in the manifest. No installation, upgrade, image pull, provider call or external forge operation was authorized or performed.

The first declaration used prose expected-output descriptions; all commands succeeded but the verifier requires matching output text. Revision 2 corrects those expected strings; all 12 entries have current accepted evidence. Package RECORD hashes identify the existing installation, not an independently authenticated upstream archive.

No new application dependency is planned. Browser fixtures use installed tools and deterministic local inputs; no external forge account is needed. If implementation requires additional software, revise the manifest and obtain separate exact installation authority before installing it.

## Feature breakdown

1. **feat_049_001 — Evidence-based recovery progress** — own the shared versioned progress contract, concurrent incident ordering, owner/claim freshness, generation-bound verification and bounded published current reads. Cover success criteria 1, 2, 4 and the producer half of 6. Freeze contract before transcript integration.
2. **feat_049_002 — Durable recovery milestones and bounded transcript history** — depends on feat_049_001. Add deterministic system-event identity, committed-source notifications, cross-process deduplication, bounded restart reconciliation, stable role-summary identity and paginated history. Cover success criteria 3, 5 and transcript half of 6.
3. **feat_049_003 — Coherent board and Historical recovery experience** — depends on feat_049_001, feat_049_002 and feat_049_004. Present the common current summary, concurrent incidents and milestones; deliver deterministic API/browser operational acceptance and reconcile affected diagrams against implementation. Cover success criteria 4, 7 and 8.

4. **feat_049_004 — Prevent stale transcript acknowledgements from regressing recovery routing** — depends on completed feat_049_002. Repair the existing acknowledgement freshness contract across private fast-path/drain and public mapping writers, with deterministic delayed-writer, rewrite/move, restart and genuine-conflict evidence. Own the affected synchronization, design and native Code reconciliation described in its canonical spec. Also correct malformed UTF-8 detail cursors that otherwise return empty nonadvancing pages, preserving the existing route and budgets. Candidate repair `ecd390f4d1819d72bc65e2ea4960000a48e50a67` is on the completed Feature 2 branch and must be reconciled through this corrective delivery path; it is not yet integrated or accepted by the Epic. Reuse and validate the candidate against the full race/restart/pending and bounded-pagination acceptance, with final fixtures for Feature 3. This correction adds no product scope.

5. **feat_049_005 — Bound transcript acknowledgement work under contention** — depends on completed feat_049_004. Own deadline-aware publisher/graph/SQLite acquisition, existing-index-only lookup, timeout-to-pending replay, deterministic contention tests and affected design/Code verification. Preserve the fence-through-commit routing protection and existing pagination contract.

Retain the three product deliverable slices and the two focused corrective slices. Feature 3 dispatch and integrated acceptance require the verified corrective delivery. Canonical Feature 3 metadata lists Features 1, 2 and 4 as dependencies. At its planning-start review, Feature 3 is active and Feature 4 is canonically completed at `a3d4a42b3df92a553206c300c42142600183eaef`; the dependency-metadata discrepancy remains closed. The Epic checkout reviewed at `573c6308` still contains the planning baseline, so completed lifecycle does not establish integrated Epic acceptance. Feature 3 must confirm the repaired source in its supported integration baseline and pin final consumer fixtures before implementation acceptance. Renewed Epic sign-off remains withheld pending integrated review, completed Task-record corrections and architecture publication recovery.

Feature 3 planning handoff: corrective evidence at `docs/feature_artifacts/task_049_004_003_closeout.md` in Feature 4 revision `a3d4a42b` reports 77 focused passes, 235 elements/283 relationships/24 views, pinned rendering and scoped Chromium Code navigation. It names `tests/war_room/test_transcript_pages_api.py` as the route/header/error/detail fixture and `tests/recovery_progress/test_transcript_milestones.py` as the receipt fixture. These are available source artifacts, not new Epic test results. The corrective branch now has `cascade/recovery_progress/DESIGN.md` and parent links; final ownership review remains an integrated check. Feature 3 replaces stale planned API prose from these exact fixtures, preserves distinct progress revision/transcript incarnation and typed pending/restart behavior, and owns the real notification-to-browser timeline with the final role reply held. Persist this and the existing diagram-impact inventory in Task acceptance before dispatch; propose an Epic amendment for any contract change. The broader browser journey's refreshed-documentation assertion remains a reported limitation distinct from the successful scoped architecture navigation probe. Architect source review of corrective revision `a3d4a42b` found that `fenced_transcript_source_acknowledgement` still uses blocking thread/OS graph locks and `_connect_index` with a 30-second timeout and schema initialization. The fence-through-commit routing repair does not establish the required 250 ms fast-path and one-second drain bounds under contention. Feature 5 now owns the corrective handoff for deadline-aware acquisition/lookup, pending replay without cursor loss, contention regressions and reconciliation of `REQ-RECOVERY-PROGRESS-004`; completed Feature 4 lifecycle does not close this acceptance gap. Feature 3 retains independent consumer scope and cannot compensate with UI inference. Supported corrective delivery is assigned to feat_049_005. Feature 3 may continue independent consumer implementation against the pinned Feature 4 fixtures; final Feature 3 and Epic acceptance require Feature 5's integrated repair and contention/replay verification. This is an acceptance gate, not a claim that Feature 3 dependency metadata was changed.

Final Feature 4 handoff `feat_049_004:feat_049_004_integrated_handoff_a3d4a42b_20261126` pins `a3d4a42b3df92a553206c300c42142600183eaef`, containing atomic routing baseline `469f0fa5f0bd99cf38351e26d6d7feb952bb26d3` and UTF-8 baseline `ecd390f4d1819d72bc65e2ea4960000a48e50a67`. The Feature owner reports 69 focused tests in 76.62 s on that head; source validation reports 235 elements, 283 relationships and 24 views. Exact consumer fixtures are `tests/war_room/test_transcript_pages_api.py::test_typed_invalid_restart_pending_and_get_is_projection_only`, `::test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor`, `tests/recovery_progress/test_transcript_milestones.py`, and `tests/war_room/test_durable_chat_store.py::test_fenced_source_lookup_leaves_pending_intent_for_writer_repair`. These are child-reported results; the Epic has inspected the source/artifact but has not rerun the suite or integrated that revision.

Do not create a standalone speculative framework, streaming subsystem, generic event bus, recovery scheduler or unrelated UI redesign. Feature teams translate their scope and diagram rows into Task acceptance criteria before task dispatch.

Feature 4 architecture handoff reports durable pending operation `architecture-publication-ada28defde68702ee43f44a9d1da09d8f89ea916b93fee142c85ab7e22fc974d`, pinned to completed plan `a3d4a42b3df92a553206c300c42142600183eaef`, `cascade/war_room/DESIGN.md` and that revision's `workspace.contract.json`, `workspace.dsl`, `model.dsl` and `views.dsl`, with expected accepted-lineage generation null. The authorized architecture owner must replay the exact saved proposal to discover completion; a newer reference is not a retry and pending is not accepted publication. This is separate from the Epic's existing publication recovery. Pinned-tree review confirms `architecture/design-mappings.json` still maps `cascade/recovery_progress` to `cascade/DESIGN.md`, while the child design owns `REQ-RECOVERY-PROGRESS-001..004` and `DEC-RECOVERY-PROGRESS-001..002`. During supported Epic integration, the Epic Architect owns persisted design mapping/ownership reconciliation against the integrated child and package/Watchdog links, including source/model ownership validation. Do not add a mapping to an absent child design in the current Epic planning baseline or rewrite the pending publication references. Design-owner completeness and renewed sign-off remain withheld until the mapping and final source-linked design review agree.

Feature 5 implementation handoff reviewed at `4959f09f342b2c6280a13b5657aa4f062a34da2e`: implementation `1334c4a12cfb65f2442613ad97583ee583676223` is in Feature ancestry but outside Epic ancestry. Source/design review confirms shared-deadline propagation through publisher, transcript and lifecycle lock paths and an existing-index-only fenced lookup. This is not integrated contention acceptance. Feature 5 reports Task 1 completed and Task 2 active; Task 2 retains exact integrated-baseline, measured contention/replay, consumer and native Code/design verification. The reported duplicate template placeholders in completed Task 1 remain an unresolved canonical-record correction; Epic `read_doc` returned `content_access_denied`, so their exact contents were not independently verified or accessed through a fallback. The Feature team has been asked to preserve the corrected body and any lifecycle refusal. Existing acceptance, ownership-mapping and publication gates remain unchanged; no new scope or renewed sign-off follows from this handoff.

Integration checkpoint at Epic `552945ad`: Feature 4 revision `a3d4a42b` is now an Epic ancestor. Feature 3 candidate `d05eca4f` is not an Epic ancestor; its delivered source is present through the integrated tree, so source equivalence must not be described as candidate-commit ancestry. The integrated `cascade`, `architecture` and `tests` trees are byte-equivalent to reviewed Feature 3 revision `99be54b1`, although that plan revision and later lifecycle/closeout revisions are not Epic ancestors. Feature 5 implementation `1334c4a1` remains outside Epic ancestry; blocking graph locks and the 30-second schema-initializing transcript lookup remain on this baseline. Focused verification and design review are recorded in the owned architecture evidence; final contention acceptance still requires Feature 5 delivery. The Recovery Progress child design is now present, so the Epic Architect can reconcile its persisted design-owner mapping against the integrated source. Feature 3 reports canonical closeout revision `334320ba` now records its terminal publication failure; this turn's canonical Feature read returned `content_access_denied`, so the reported canonical update is not independently confirmed. The exact failed request and existing attributed terminal failure remain preserved. No architecture approval, scope change or renewed sign-off follows from lifecycle completion or these merges.

Integrated verification on the `9affeb7f` product baseline: the focused publisher, milestone, durable transcript, paginated HTTP/Chromium and C4 source suite returned 75 passed and one failure in 93.65 seconds. `test_receipt_retry_refreshes_registered_room_move_incarnation` reached correct stored acknowledgement assertions but lacked the current projection pointer; an isolated rerun passed in 1.35 seconds. The fast path may leave dirty projection work after its deadline, so this is an unresolved timing/replay verification gap rather than a confirmed routing regression or a clean suite. Feature 5 must demonstrate eventual drain/publication on its repaired integrated baseline and keep timing tolerances distinct from measured results. The Node browser refresh-race harness passed; all twelve saved publication digests match. Acceptance and renewed sign-off remain withheld.

Architect ownership reconciliation at `7f24245c`: the integrated Recovery Progress child now owns its persisted `architecture/design-mappings.json` row and owner-scoped artifact identity. Parent and Watchdog links already agree; requirement/decision IDs retain a single owner. The child verification table now explicitly distinguishes cooperative deadline checks from unverified elapsed contention bounds on this Epic baseline. All 33 mapped designs and the reviewed local file links resolve; architecture destination/source checks passed 30 tests in 3.11 seconds, all twelve saved publication digests match, and diff checks passed. This closes the current persisted mapping gap only. Feature 5 integration and measured contention/eventual projection publication, completed-record corrections, broader documentation-refresh proof and fresh exact architecture publication remain gates. No saved publication pin, accepted snapshot or sign-off was changed. Detailed diagram-impact and source-flow review is in the owned architecture evidence.

## Verification and acceptance

Use focused API/storage integration tests plus one real-browser fixture journey; no blanket full-suite mandate or mock-only replacement for concurrency/restart evidence.

- Replay the supplied 03:58:01 request, 03:58:10 acknowledgement and 04:02:25 attempt start with fixed event times. Hold the role's final reply pending. The start milestone must already be observable through supported HTTP/UI paths and both current views must identify the same action, generation and live attempt.
- Exercise queued-but-idle, acknowledged-but-no-live-owner, a live investigating turn, live repair, explicit checks/publication waits, expired claim, proven-dead and inaccessible owner, failure/retry, exhausted allowance, new generation and independent same-generation verification. Successful publication alone stays verification pending.
- Race two actual writer processes and duplicate notifications; restart at each source/chat/cursor commit boundary. Exactly one milestone exists per source transition, ordered and attributed correctly. Preserve distinct same-text role summaries while suppressing replay of the same summary.
- Cover unknown legacy times, missed notifications, duplicate receipt delivery, conflicting source evidence, concurrent older/newer incidents, stale poll responses, owner graph movement and split roots. Preserve history and expose pending/incomplete evidence rather than health.
- Instrument recovery-related GETs to assert zero writes, graph creation/checkpoint access, raw-ledger/full-transcript scans, provider/Git/process probes and added agent turns. Demonstrate page/source/response limits with a large deterministic fixture; test cursor expiry and load-older without duplicates or loss.
- Exercise safe rendering and links, keyboard navigation, scroll preservation, current-summary visibility and direct transcript anchors in Chromium. Follow actual supported routes; fixture writes cannot substitute for the notification path under test.
- Reconcile designs/model/contracts with the final diff. Verify native Code navigation and pinned source links as specified in the inventory. Measure bounded reads and warm reuse; record actual commands/results and any unresolved limitations in work records.

### Planning checks and limitations

- `python -m pytest -q tests/war_room/test_recovery_incident_projection.py tests/war_room/test_planning_transcript.py tests/war_room/test_chat_poll_routing.py tests/war_room/test_projection_batching.py`: **15 passed in 2.14s**. These verify the existing baseline only; several encode the coarse investigating semantics that implementation will deliberately replace.
- `validate_c4_workspace(Path("architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5"))`: **C4WorkspaceContract validated** for current authored sources.
- Existing Chromium launched and closed successfully; the pinned Structurizr image was inspected locally. No new browser product acceptance, rendered architecture change, or Code-navigation check was run. Those remain explicit owner obligations; a valid existing contract does not close the recovery/transcript Code coverage gap.
- All three feature records were read back through Cascade: backlog status, dependency order and requested Codex/model/reasoning selections are preserved. No Tasks were minted or dispatched, and no runtime implementation was changed.

## Open questions

### Architecture review and handoff

The four manager questions are resolved by the selected protocol above, current-code model/design expansion, and this evidence boundary: review uses only this owned checkout and permitted canonical projections. Historical records and accepted review ancestry for epic_044/epic_048 remain outside scope; no additional dependency or claim about those deliveries follows from the inspected code. The observed timeline remains a user-supplied deterministic acceptance fixture.

Reviewed owning designs: `cascade/war_room/DESIGN.md` (current summary/history limits, source-linked functions and return/interruption sequence), `cascade/task/DESIGN.md` (source transaction, attempt and claim lifecycle), `cascade/workspace/DESIGN.md` (queue/lock evidence and graph-return handoff), `cascade/DESIGN.md` (shared interfaces and navigation). Added current implementation coverage and stable local evidence requirements; removed a stale baseline inventory from the War Room design. Reviewed the root audit/context/container contract and Watchdog producer/postcheck sections: their topology, authoritative verification and immutable audit ownership are unchanged because this planning diff adds documentation/model coverage of existing calls, not a new runtime or health setter. No proposed projection, append protocol or live proof is described as implemented in DESIGN.md.

Planning model changes add 13 current Function nodes, nine relationships, component-to-design links and inclusion in `cascade-dashboard-code`, `cascade-task-code`, and `cascade-workspace-code`; source contract and view declarations change together. Landscape/context/container topology is unchanged (same operator, provider/forge and repository, same runtime boundaries). Supervisor/team components retain their ownership; Dashboard responsibility text now names its existing recovery/history consumers. Watchdog and Teams Code views already expose stage receipts, postcheck and publication; no current source symbol changes there. Each Feature must reconcile its inventory row with implemented code and carry this protocol and navigation/failure acceptance into Tasks. Current-source coverage is a reviewed planning baseline, not evidence that the proposed product behavior works.

Architecture verification results and pinned publication references are recorded in [the owned review evidence](../../epic_artifacts/epic_049_architecture_evidence.md) and `docs/epic_artifacts/epic_049_architecture_review.json`. The three backlog Feature specs now carry the selected protocol as required Task acceptance, replacing their unresolved architecture handoff text. A bounded architecture HTTP paging correction is implemented on this owned branch because the expanded real model exposed an existing page-size assumption: the default response measured 271,703 bytes against the unchanged 262,144-byte limit. The browser and document-context consumer follow smaller pages; the route still refuses metadata plus a single view when they cannot fit. This correction does not implement the proposed recovery progress pipeline. Remaining implementation acceptance belongs to the three sequenced Features; manager sign-off follows review of this revised Epic. No implementation dispatch is requested by this review.

## Decision log

- 2026-11-14 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-25 · Epic Manager · **Core dependencies**
  Chose Validate this epic on the existing local Linux x86_64 host with manifest revision 2; no software installation or upgrade..
  Rationale: Brief and repository require Python runtime packages, pytest, Node, Chromium/Playwright and the pinned Docker/Structurizr renderer. All 12 declared existing installations have accepted verification evidence. The declaration identifies local validation only and does not attest deployment or upstream package provenance.
  Honors: Dependency declaration before planning; exact target identity; separate installation authority..

- `dec_002` · 2026-11-25 · Epic Manager · **Macro-architecture**
  Chose Use one evidence-based public progress contract and deterministic transcript milestones from existing durable recovery sources; split delivery into projection, persistence/history and UI acceptance features..
  Rationale: Current projection collapses queueing into investigating; transcript append happens after role return and lacks cross-process event identity. Producer-owned projection and committed-source notifications address those gaps without changing recovery authority or adding paid turns. Architect must resolve exact storage, notification and crash protocols before final sign-off.
  Honors: Success criteria 1–8; preserve generations, transcript history and existing repair/verification gates; bounded read-only GET..

- `dec_003` · 2026-11-25 · Epic Manager · **Open questions**
  Chose Hand the saved plan and three backlog feature contracts to the Epic Architect before final role sign-offs.
  Rationale: Projection storage/notification hooks, cross-process transcript replay/cursor protocol and integrated recovery/transcript Code coverage need concrete architecture review. Baseline checks passed (15 tests and current C4 source contract); historical evidence for the two related epics was denied by owner scope and was not accessed through a fallback.
  Honors: Design skill implementation-depth and review contract; no premature sign-off, dispatch or bypass of scoped content access.

- `dec_004` · 2026-11-25 · Epic Architect · **Macro-architecture**
  Chose Use work-addressed immutable progress pages, a writer-only derived SQLite index, and source-committed transition receipts drained by the existing supervisor plus an attempt-start fast path..
  Rationale: Bounded GETs cannot scan action history; polling and post-turn summaries cannot expose a live attempt. Retained source identities close the source-commit/notification crash gap. Explicit invocation/executor tokens avoid treating unfinished queued work or a live PID as executing repair. Existing recovery stores and postcheck retain authority.
  Honors: Success criteria 1–6; no new scheduler, repair policy, paid turn or dependency; explicit source-ledger loading and stale-evidence limits..

- `dec_005` · 2026-11-25 · Epic Architect · **Macro-architecture**
  Chose Preserve room JSONL with a stable graph OS fence, durable append intent, derived unique-key/offset index, and immutable read pages; bind role replies to checkpoint lineage/message identity..
  Rationale: A process-local lock and author/body matching cannot provide cross-process uniqueness or restart correctness. Intent, fsync and index commit ordering make partial append and post-append crashes replayable without duplicating events. Stable tracking-root fencing covers room moves and split roots.
  Honors: Success criteria 3, 5–7; occurrence time remains separate from append time; legacy history retained; bounded paginated GET; source failures never authorize repair..

- `dec_006` · 2026-11-25 · Epic Architect · **Open questions**
  Chose Publish a diagram-change planning baseline with real recovery/transcript Code nodes and current-design limits; assign future producer/replay/UI reconciliation and acceptance to the three sequenced Features..
  Rationale: The generic Dashboard view omitted current recovery and transcript implementation paths. Current functions can be modeled truthfully now, while proposed storage and live evidence stay in work records until implemented. Context/container topology and existing Watchdog verification remain accurate. Historical accepted-lineage evidence for related epics is not available within this team's scope.
  Honors: Design skill implementation-depth, single ownership and current-fact contract; revision-pinned architecture publication; Task-level navigation, crash, freshness and operational acceptance..

- `dec_007` · 2026-11-25 · Epic Architect · **Macro-architecture**
  Chose Keep the 256 KiB architecture metadata cap and return smaller view pages with lossless continuation; make document-context lookup follow the same continuation..
  Rationale: The expanded current-code model rendered successfully but the supported browser received HTTP 413 for a 271,703-byte default page. A one-view page fits, and the existing browser already follows cursors. Adaptive page sizing fixes this concrete publication/navigation blocker without changing target identity, render bounds, accepted snapshots or process startup policy.
  Honors: Design-skill actual navigation and warm-reuse verification; bounded metadata, nonempty advancing pages, pinned source identity and typed refusal if the minimum page cannot fit..

- `dec_008` · 2026-11-26 · Epic Manager · **Corrective sequencing**
  Chose Mint feat_049_004 after completed feat_049_002 to repair stale private acknowledgements; make feat_049_003 depend on the correction and withhold integrated Feature/Epic acceptance pending verified repair..
  Rationale: In reply to feat_049_002:feat_049_002:postmerge_stale_private_ack_20261126. Source review confirms the private mapping can replace newer incarnation/sequence with a delayed saved acknowledgement. Completed lifecycle is not proof of acceptance, and an owned backlog correction is available without reopening completed records.
  Honors: Existing success criteria 4–6, durable identity/replay contract, bounded writer work, genuine conflict rejection, and design/native Code verification. No product scope expansion or completed-record edit..

- `dec_009` · 2026-11-26 · Epic Manager · **Corrective sequencing**
  Chose Route candidate ecd390f4 through feat_049_004, including the malformed UTF-8 detail-cursor correction, while retaining full acknowledgement-race acceptance and the Feature 3 sequencing hold..
  Rationale: In reply to feat_049_002:feat_049_002:postmerge_repair_ecd390f4_20261126 and feat_049_002:feat_049_002:postmerge_detail_cursor_gap_20261126. The completed Feature branch contains a candidate for both existing contract defects, but the commit is not in Epic ancestry and its sequential private-helper regression does not establish the required real writer interleavings. Reusing the candidate through the existing corrective slice avoids duplicate implementation without equating lifecycle completion with delivery.
  Honors: Existing durability/truthful-routing and bounded-pagination contracts; supported child integration; no completed-record rewrite, dependency installation, new route or product scope. Renewed sign-off and acceptance remain withheld pending sequencing reconciliation and verified delivery..

- `dec_010` · 2026-11-26 · Epic Manager · **Corrective sequencing**
  Chose Assign the existing writer-contention gap to feat_049_005 after completed feat_049_004; allow independent Feature 3 consumer work while withholding final integrated acceptance pending the bounded repair..
  Rationale: In reply to feat_049_004:feat_049_004_integrated_handoff_a3d4a42b_20261126. The pinned source and child results support atomic routing and UTF-8 continuation, but source lookup still uses blocking graph locks and a 30-second SQLite connection with schema initialization. A focused corrective child provides supported delivery without reopening completed records or hiding the existing 250 ms/one-second acceptance gap.
  Honors: Existing writer budgets, durable replay and immutable identity, graph fence through commit, no UI workaround or product scope expansion; design/Code and contention evidence before acceptance..
## Amendment log

_(none)_
