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
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-14'
updated: '2026-11-25'
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

Existing action/incident stores remain authoritative. Material transitions notify a deterministic non-model publisher after the authoritative write commits. Use the existing supervisor/audit producer lifecycle for bounded reconciliation and stale-owner refresh; do not wait for the role's final response or add a paid turn. The accepted projection storage/index layout must be settled by the Architect before sign-off; it must support work-ID-addressed bounded reads without rescanning raw action history on GET.

The milestone append path uses the owning graph's existing transcript storage, with additive event metadata and a deterministic event key bound to source record/receipt, action, generation, attempt and material transition identity. Repeated polling or a changed observation timestamp cannot mint an event. Repeated entry into the same stage within an attempt must remain distinguishable when the source records distinct material transitions.

A cross-process lock/atomic append protocol protects durable event uniqueness. Do not claim that `process_lock` alone is a multiprocess fence. Record source occurrence time separately from append/reconciliation observation time and provenance. Legacy records without reliable time say “time unavailable”; never backdate them to a fabricated timestamp. Keep final authored messages intact and give checkpoint-origin role summaries a stable identity that deduplicates direct append and restart backfill without suppressing separate identical replies.

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
| `cascade-war-room-components`, `cascade-dashboard-code` | `cascade/war_room/DESIGN.md`; `recovery_incident_from_action`, `recovery_incidents_by_work_id`, `handle_get_chat`, `read_messages`, `append_transcript_message`, `append_planning_turn_to_chat`, `sync_planning_transcript_to_chat`, board/chat UI | F1 owns progress projection nodes; F2 owns transcript writer/page nodes; F3 reconciles route/UI nodes and code navigation. Current dashboard Code view only covers generic HTTP/audit paths, so recovery/transcript implementation coverage is a material gap to close. |
| `cascade-task-code` | `cascade/task/DESIGN.md`; `acknowledge_team_recovery`, `_claim_resume_attempt`, `finalize_attempt`, `record_action_checkpoint`, `resume_action` | F1/F2 show committed transition boundaries, claim/attempt identity and notification ordering without changing repair policy; verify normal claim and interrupted attempt against source. |
| `cascade-watchdog-code` | `cascade/watchdog/DESIGN.md`; `incident_record`, `recovery_stage_receipt`, `publish_audit_projection`, postcheck integration | F1 shows safe evidence projection/freshness and generation verification; F2 shows bounded reconciliation scheduling if wired here. Existing audit pipeline and required new paths must be distinguished. |
| `cascade-workspace-code`, `cascade-teams-code` | `cascade/workspace/DESIGN.md`, `cascade/DESIGN.md`; `graph_turn_owner_is_live`, kickoff transcript calls and review publication | F1/F2 trace live owner observation, role-return/backfill, restart and source-root routing. Preserve component ownership: a symbol has one Code owner; cross-component references link to it. |
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
3. **feat_049_003 — Coherent board and Historical recovery experience** — depends on feat_049_001 and feat_049_002. Present the common current summary, concurrent incidents and milestones; deliver deterministic API/browser operational acceptance and reconcile affected diagrams against implementation. Cover success criteria 4, 7 and 8.

Keep these three deliverable slices. Do not create a standalone speculative framework, streaming subsystem, generic event bus, recovery scheduler or unrelated UI redesign. Feature teams translate their scope and diagram rows into Task acceptance criteria before task dispatch.

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

Manager assessment reviewed `DESIGN.md`, `cascade/DESIGN.md`, `cascade/war_room/DESIGN.md`, relevant Task/Watchdog/Workspace sections, the C4 view inventory and source boundaries listed above. No runtime or DESIGN.md edits are made by this planning pass; current files must not falsely describe proposed functionality as implemented. The plan routes implementation ownership to the three features.

Before final plan sign-off, the Epic Architect must settle and record:

1. The exact materialized progress storage/index and supervisor notification/reconciliation hook. It must meet bounded reads and attempt-start visibility while a long role turn is still active, without rebuilding all audit history per transition.
2. The cross-process transcript append/deduplication and cursor crash protocol, including role-summary identity and the legacy bounded GET compatibility shape.
3. The baseline Code coverage gap for recovery/transcript paths: complete source-linked current coverage or explicitly scope and justify the proposed architecture review, with model/contract edits and navigation evidence required from owning Tasks. Review new requirement ownership and all affected design interfaces.
4. The permissible evidence for overlap with epic_044/epic_048, or the precise residual provenance limitation. Their scoped historical-record denial is not a dependency-status result.

These are architecture decisions, not requests for installation or generic human permission. Manager final sign-off follows review of the resolved architecture and final Epic revision; no implementation dispatch is requested in this turn.

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
## Amendment log

_(none)_
