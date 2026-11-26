---
id: feat_049_002
title: Persist recovery milestones and bounded transcript history
tier: feature
status: completed
parent: epic_049
children:
- task_049_002_001
- task_049_002_002
- task_049_002_003
- task_049_002_004
- task_049_002_005
depends_on:
- feat_049_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 032809336f3fcf3810c7270c28195da9c85a3bf6
created: '2026-11-25'
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
approved_at: '2026-11-25T22:35:29.872481+00:00'
---




# Persist recovery milestones and bounded transcript history

## Parent Epic

epic_049

## Scope

Deliver epic_049 success criteria 3, 5 and the transcript half of 6 using Feature feat_049_001's common progress contract.

Required Task acceptance:
- After authoritative action/incident commits, publish concise System · Recovery milestones before the manager/architect turn completes. Cover request, acknowledgement, attempt start, supported stages, waits/failures, publication and independently verified completion. Do not generate narrative progress from a model.
- Use owning-graph transcript storage with additive event metadata, stable source references, occurrence time separate from append/reconciliation time, action/generation/attempt identity and deterministic transition keys. Distinct repeated stages need distinct source identities; observation timestamps alone cannot mint milestones.
- Specify and implement a cross-process atomic append/deduplication fence; existing process_lock alone is insufficient. Reconcile source-committed/chat-missing and chat-appended/cursor-not-advanced crashes through bounded resumable supervisor work. Failure to write chat preserves action evidence and never changes repair admission. No GET reconciliation, full-history polling, added recovery scheduler or extra paid turn.
- Preserve authored final summaries; deduplicate direct append/restart backfill by stable source message/checkpoint identity without suppressing separate identical authored messages. Label unknown legacy occurrence times and reconciliation provenance honestly.
- Freeze a versioned paginated chat interface with default 50/max 100 rows, 1 MiB source and 256 KiB serialized budgets, explicit continuation and cursor generation. Preserve legacy array shape through a bounded latest window with explicit continuation metadata. Never silently truncate or delete old history. Wrong/stale cursors return typed restart. Support incremental poll and load-older.
- Route to the owning epic/feature graph across dispatch/completion and split product/tracking roots; never place an event in another team's transcript.
- Exercise two actual concurrent writer processes, duplicate notifications, restart at each commit boundary, malformed/torn append behavior, missed transitions, unknown legacy times, distinct repeated stages, stable role deduplication, cursor overflow/expiry and large-history budgets. Assert reads do not append, open checkpoints or probe providers/Git/processes.

The parent Epic fixes the append/index/cursor protocol and compatibility shape; Feature planning must turn it into exact Task APIs before implementation.

Design/Code ownership: War Room transcript requirements, chat_store.py, planning_transcript.py, sidecar_routes.py and their native cascade-dashboard-code nodes; Task source notifications in cascade-task-code; kickoff owner/role-return boundaries in cascade-workspace-code/cascade-teams-code; Watchdog reconciliation in cascade-watchdog-code when used. Update owning designs, parent links, model.dsl, views.dsl and workspace.contract.json with real symbols/kinds. Show normal and crash replay sequences, persistent state, error behavior and source/design links. Verify integrated Code/Level up/deep links and pinned sources; do not overwrite accepted artifacts.

Preserve Codex feature_lead/feature_architect gpt-6-sol high and SWE gpt-5.6-sol medium. Use verified existing software; no installation or premature dispatch.

Architecture contract resolved by Epic decisions dec_004–dec_006. Required Task acceptance additionally implements the Epic's Selected storage and execution contract: stable tracking-root graph OS fence across all append/remove/sync writers; JSONL authority; durable pending-line intent plus SQLite event/offset index; fsync-before-index-commit and acknowledgement after fence release; exact-tail crash repair; immutable bounded read pages; incarnation and append-sequence cursors; resumable legacy import with honest unknown occurrence times; checkpoint-lineage/message-ordinal reply identity; routing handoff under the same fence. Include every crash injection and real two-process race in the Epic matrix. Freeze concrete versioned route/header names, Link continuation and typed legacy-unavailable response before dependent UI dispatch.

## Data structures

### Producer input agreement

The completed Feature 1 serializer and Task 4 fixtures confirm sorted compact JSON receipt IDs with all 13 identity keys, nullable incident/attempt/claim fields, retained-order deduplicated affected work IDs and excluded occurrence/payload; entry ID hashes canonical action, generation and nullable attempt. Consume both IDs unchanged. Safe v1 entries include the listed fields with null occurrence for legacy evidence, string/null prerequisite and sanitized target, modern or legacy_unknown provenance, ordered receipt_refs and empty milestone_refs until durable append. Agreement was sent through epic_049. Pinned producer source is feat/feat_049_001 revision dc47068cebf5643c319d37785edf35882fb96941. The final fixture is tests/war_room/fixtures/recovery_progress_v1_epic_044.json, with tests/war_room/test_recovery_progress_api.py and tests/war_room/test_http_read.py. The fixture covers one waiting blocker and empty milestone_refs, not the full operational timeline. Successful responses include entry_count and entries carry schema_version and entry_revision; pending omits entry_count. A revision_changed 409 carries both previous_revision and current_revision. Task 2 must verify its live mapping against these producer files.

### Transcript v1 storage

The owning graph JSONL remains authoritative. Existing id, graph_id, author, body and append-time ts remain; additive event_schema_version, kind (recovery_milestone|role_reply|human), deterministic source_key, nullable occurred_at, appended_at and provenance (direct|reconciled|legacy_unknown) identify new lines. A recovery line carries unchanged receipt_id and entry_id plus action_id, generation, nullable attempt_number, safe target and source_reference. Body comes only from allowlisted source/progress fields. One receipt maps to one stable message ID; distinct retained transition sequences produce distinct lines.

A graph-scoped OS advisory lock lives under the canonical tracking runtime root across checkout moves. Every append, explicit sync, human rollback/rewrite and migration writer cooperates. A writer-only SQLite index at .cascade/transcript_index/<sha256(graph-id)>.sqlite tracks unique source/message keys, append sequence, JSONL byte offsets and lengths, incarnation, indexed end, fair replay/import cursors and one durable pending exact-line intent. Under the fence: resolve the registered owning room and incarnation; reconcile a pending intent against only the exact tail; commit intent with expected offset and digest; append and fsync JSONL; transactionally commit key/offset and clear intent; release the fence; then acknowledge the source. Unexpected bytes or ambiguous routing remain pending without truncating unrelated history. Room movement copies committed history and switches incarnation under this same fence. No source lifecycle lock is held while taking the graph fence.

The index publishes immutable bounded read pages with a direct graph pointer. Legacy import advances by at most 1 MiB/100 rows per pass, retains original UUID and append time, leaves source occurrence null, and reports incomplete coverage until finished. Oversize legacy rows expose a bounded labeled preview and chunk-detail continuation. Authored role reply keys use checkpoint lineage and persisted message ordinal or durable message ID, shared by direct append and backfill. Separate identical replies stay separate; ambiguous legacy body matching is explicitly labeled legacy_unknown rather than claiming exact deduplication.

## API contracts

The completed producer route remains GET /api/recovery/progress?work_id=<id>&cursor=<opaque>. Its envelope, invalid_request 400, revision_changed 409 restart, pending evidence codes, sanitization and ordered references are consumed unchanged. milestone_refs names only a JSONL message whose unique key/offset committed after fsync; pending delivery leaves it empty. Task 2 owns append_committed_recovery_receipt(root, receipt, snapshot): after the source lock is released, it returns a durable acknowledgement with receipt_id, entry_id, graph_id, message_id, incarnation and append_sequence, or a typed pending result. The graph index keeps the receipt-to-message key/offset across a crash after append and before source acknowledgement. The supervised replay cursor retries the same receipt_id; exact-tail repair and the unique key return the same acknowledgement without a second line. After fence release, the consumer persists the receipt_id-to-entry_id/message_id mapping in the producer writer index and republishes dirty aliases. The fast path and bounded replay call publisher._record_transcript_milestone inside their existing publisher transaction; record_transcript_milestone(root, ack) is the separate public mapping entry point. Publisher _upsert merges only committed mappings for the entry's retained receipt_refs into ordered milestone_refs; a failed publisher update is replayed from durable graph acknowledgement. The source cursor advances only after acknowledgement and publisher mapping are durable. No GET repair or source-ledger lock under the graph fence.

Transcript v1: GET /api/transcript/v1/<graph_id>?direction=older|after&cursor=<opaque>&limit=<n>. With no cursor, return the latest 50 rows; limit is 1–100. The versioned envelope has schema_version:1, exact graph_id, incarnation, high_water_mark, completeness (complete|incomplete|pending), observed_at, ordered items, older_cursor, after_cursor and has_more. Older pages hold their initial high-water; after pages advance from the committed append sequence. Opaque cursor binds graph, incarnation, direction, position and older high-water. Invalid query/cursor/foreign graph is 400 invalid_request; moved or rewritten room/expired page is 409 cursor_restart with restart:true, current_incarnation and restart_url. Unbuilt/corrupt/unsafe index is 503 history_pending with retryability and completeness. Typed errors carry schema_version, graph_id and error.code/message/retryable.

Legacy GET /api/chat/<graph_id> retains an array, limited to the latest window. Link: </api/transcript/v1/<graph_id>?direction=older&cursor=<opaque>>; rel="next" gives older continuation; X-Transcript-Completeness, X-Transcript-Incarnation and X-Transcript-Has-More describe it. Unavailable history is typed 503 transcript_unavailable, never a healthy empty array. Valid empty history may return []. Both reads use direct no-follow regular-file pointer, manifest and requested immutable pages only, bounded to 100 rows, 1 MiB aggregate source and 256 KiB serialized response. GET never opens writer SQLite, scans JSONL, imports, reconciles, opens graph checkpoints or probes provider/Git/process state. Oversize legacy detail is GET /api/transcript/v1/<graph_id>/items/<message_id>/detail?cursor=<opaque>. An item with detail_truncated:true supplies detail_url and detail_cursor; the endpoint returns schema_version:1, graph_id, message_id, incarnation, encoding:utf-8, a UTF-8-aligned chunk of at most 64 KiB, next_cursor and complete. Its cursor binds graph, incarnation, message ID, immutable detail digest and byte offset; no caller path is accepted. The endpoint reads only a requested immutable chunk through the direct pointer/manifest, under the same 1 MiB source and 256 KiB response caps. Invalid cursors give 400 invalid_request; changed incarnation or detail digest gives 409 cursor_restart; unavailable detail gives 503 history_pending. No extra paid turn or recovery scheduler is introduced.

## Logic flow

```mermaid
sequenceDiagram
    participant S as Committed Task/Watchdog source
    participant P as Supervised consumer
    participant F as Graph fence and intent index
    participant J as Owning JSONL
    participant R as Immutable read pages
    S-->>P: Notify after source lock release
    P->>F: Fence graph, resolve owner, dedupe source key
    F->>F: Repair matching pending intent/tail
    F->>J: Append safe line and fsync
    F->>F: Commit key/offset and clear intent
    F->>R: Publish bounded pages
    F-->>P: Release graph fence
    P->>S: Acknowledge; expose milestone ref
    alt Missed notification or restart
        P->>S: Resume retained-receipt cursor
        P->>F: Replay same key without duplicate line
    else Ambiguous route or unexpected tail
        F-->>P: Pending and lag; preserve source
    end
```

## Task breakdown

1. `task_049_002_001` — fenced storage and room migration.
2. `task_049_002_002` — committed-receipt milestones (depends on 001).
3. `task_049_002_003` — authored reply identity (depends on 001).
4. `task_049_002_004` — bounded history/API acceptance (depends on 001–003; final acceptance also requires repair 005).
5. `task_049_002_005` — replay durability and crash-safe room movement repair (depends on 001).

| Slice | Owns | Depends on |
|---|---|---|
| Durable transcript store | Graph OS fence, intent/index, exact-tail repair, legacy import and room movement | — |
| Recovery milestone consumer | Receipt mapping, safe live milestone append, supervised bounded replay and refs | Store |
| Authored reply identity | Checkpoint-lineage direct/backfill identity and human rollback | Store |
| Bounded history API and acceptance | Immutable pages, v1/legacy reads, concurrency/crash/budget acceptance | Store, milestones, replies and repair |
| Store crash repair | Full-tail fsync replay and resumable room movement after each process-death boundary | Store |

Diagram impact inventory: cascade-context and cascade-containers: API Task verifies unchanged operator/external and War Room/supervisor/repository boundaries, correcting actual relationship labels if needed; no new deployed service. cascade-war-room-components and native cascade-dashboard-code: Store Task owns fence/index/routing symbols; milestone Task owns serialization/replay and recovery_progress.publisher acknowledgement/ref-mapping symbols; reply Task owns direct/backfill symbols; API Task owns page/reader/route symbols. cascade-team-components/cascade-task-code: milestone Task checks after-lock source notifications and acknowledgement. cascade-supervisor-components/cascade-workspace-code and cascade-watchdog-code: milestone Task checks startup/tick drain and routing; reply Task checks kickoff/role-return lineage. cascade-teams-code: reply Task checks Epic/Feature checkpoint identity. War Room design owns public transcript requirements and normal/crash replay; Watchdog design owns the producer publisher boundary and its native cascade-watchdog-code nodes, with the separately routed cascade/recovery_progress child-design ownership gap acknowledged; Task, Watchdog and Workspace designs own local write, supervisor and routing facts with links to War Room. Root/package designs summarize boundaries. Source contract, model.dsl and views.dsl change together; every new Code node uses real cascade.codeComponent, cascade.parent, cascade.sourcePath, cascade.sourceSymbol and declaration kind.

Planning design review: read DESIGN.md, cascade/DESIGN.md, cascade/war_room/DESIGN.md, cascade/task/DESIGN.md, cascade/watchdog/DESIGN.md, cascade/workspace/DESIGN.md and the pinned model/views/contract against current code. The integrated store and War Room/Workspace designs describe the graph fence, JSONL intent/index and room movement. The integrated Task 5 review below records the two repaired crash paths and rewrite recovery; Task 4 owns final API and cross-slice acceptance. Milestone consumption, authored reply identity and bounded read pages remain separate Tasks. Tasks must reconcile final source and owning designs without delivery history, validate source contract and local render, and verify context → containers → component → native Code, Level up, deep-link restore and pinned source opening. Trace normal append plus crash/restart, stale symbols/ownership, warm reuse and render bounds; record actual paths, checks and gaps in closeout. Do not overwrite accepted architecture snapshots.

## Integrated Task 1 acceptance review

Task 1 merged at bd152f61d39912f920830250c62efc57050d689c. Feature acceptance remains open for two durability gaps: full-line pending-intent replay can clear the intent without fsync, and room movement can remove the source before the owner/index transition is recoverable. The focused correction belongs to task_049_002_005. Tasks 2 and 3 retain their independent implementation scope, but neither can be accepted against the shared store until Task 5 demonstrates repaired durability and restartable room movement. Task 4's integrated crash acceptance must include that result. Required fault evidence covers a fully matching tail synced before index commit, fsync failure retaining pending intent, and process death around durable copy, source removal, owner switch, terminal checkout retirement and index/incarnation reset. Recovery must preserve one routable history without duplicate append or unrelated truncation. The completed Task 1 record still has TBD acceptance/files/test/out-of-scope fields and a stale Parent Feature link. The exact requested correction, source trace and design-impact review are in [the Task 1 acceptance artifact](../../feature_artifacts/feat_049_002_task1_acceptance_review.md). This artifact does not replace the canonical Task record; its authorized correction remains open. Context/container boundaries did not change. War Room and Workspace designs plus native Dashboard/Workspace Code views require reconciliation against the repair before Feature sign-off.

## Integrated Task 3 acceptance review

Task 3 is merged on the feature branch at 4b367dee. Focused Epic/Feature graph and War Room transcript/store tests passed (35 tests), and the pinned C4 source contract validated 226 elements, 262 relationships and 24 views. Reviewed `cascade/epic/DESIGN.md`, `cascade/feature/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`, the native Dashboard/Teams/Workspace Code source and the changed implementation. Direct append and checkpoint backfill share persisted reply IDs; separate same-text replies remain distinct, and ambiguous legacy matches retain `legacy_unknown` provenance. No actor, container or component ownership changed; Code source/relationship edits cover the new rewrite boundary. Feature acceptance remains gated on Task 5's shared-store repair and Task 4's integrated checks.

A further process-death gap exists in `chat_store.py::_rewrite_messages`, used for failed human-ingest rollback and legacy labeling. It fsyncs a replaced or removed JSONL file before resetting SQLite events, indexed end and incarnation. Death between those steps leaves old index offsets against new bytes. The next writer then rejects a shorter file or starts legacy import in the middle of a longer row. Task 5 owns durable rewrite recovery or an equivalent protocol under the existing JSONL/index contract, with fault injection after replacement and before index reset; Task 4 must verify stable routing, source-key preservation and incarnation change. This is a source-traced gap, not a completed fault-injection result.

## Integrated Task 2 acceptance review

Task 2's receipt consumer and publisher mapping are integrated on the feature branch. Reviewed `cascade/war_room/recovery_milestones.py`, `cascade/war_room/chat_store.py`, `cascade/recovery_progress/publisher.py`, `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`, and the pinned model/views/source contract against the merged diff. Focused milestone, publisher and durable-store tests passed (35 tests); source-contract validation found 228 elements, 268 relationships and 24 views. Context, container and component ownership remain unchanged; native Dashboard and Watchdog Code views add the receipt append and publisher mapping functions. The designs trace committed source notification, graph append and durable mapping; UI Code navigation, Level up, deep-link and pinned-source checks remain for final integration.

The current consumer appends one line per receipt and orders `milestone_refs` from retained receipt references. A direct retry after a fenced transcript rewrite changes incarnation raises `ValueError: receipt maps to a different transcript acknowledgement`: `publisher._record_transcript_milestone` compares the original incarnation and append sequence with the graph index's new acknowledgement, even when the receipt and message ID are unchanged. A local reproduction published one receipt, changed an unrelated role line with `mark_message_legacy_unknown`, then published the same receipt. Task 4 owns the mapping fix and duplicate-receipt test across rewrite and room movement. Immutable receipt_id, entry_id, graph_id and message_id must still reject a genuine conflict; current incarnation and append sequence may change after a fenced rewrite or move. A delayed acknowledgement from the old incarnation must not replace newer routing metadata. Task 5 must preserve source keys and message IDs during its crash-safe store repair. The Watchdog design and this Feature's API prose also need to distinguish the fast path's private mapping call from the separate public `record_transcript_milestone` entry point. Task 2 and Feature acceptance remain open pending these corrections, Task 5's durability evidence, and Task 4's integrated checks.

## Integrated Task 5 acceptance review

Task 5 merged at a32d84ab8c1c109dcc6d073ad2d05728f296a126; the reviewed feature HEAD is 4d3b54e476c1688800ab6e80cac457038161efdb. Under the graph fence, `_repair_pending` fsyncs a fully visible intended line and its parent before `_commit_intent`; an fsync failure retains the pending intent. Room movement persists a fingerprinted move intent and target incarnation before copying, then resumes across copy, source removal, owner switch and index reset. Terminal retirement can finish the retained intent when the old checkout is gone. A rewrite intent similarly records exact replacement bytes and target incarnation before JSONL replacement, so restart accepts only matching original or replacement bytes and reimports retained source keys and message IDs. Conflicting bytes remain pending.

Reviewed `cascade/war_room/chat_store.py`, `cascade/workspace/integration_worktree.py`, `cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`, and the pinned model, views and source contract against the merged diff. The normal and restart sequences and persistent state agree with source. Context, container and component boundaries remain unchanged because actors, runtimes, stores and ownership did not change. `cascade-dashboard-code` updates the index, rewrite and move semantics; `cascade-workspace-code` retains the retirement owner. The new `resume_transcript_room_move` entry point is source-linked in War Room design but lacks a distinct native Code node and retirement relationship; Task 4 owns final Code reconciliation and Explore, Level up, deep-link and pinned-source checks. This is an open architecture coverage item, not an accepted final view.

Integrated validation: `pytest -q tests/war_room/test_durable_chat_store.py tests/workspace/test_integration_worktrees.py tests/workspace/test_c4_source.py` passed 70 tests; the real pinned renderer cache test passed; `validate_c4_workspace` accepted the pinned source; `git diff --check` was clean. Tests exercise complete-tail sync ordering and fsync failure, move restart boundaries, split roots, terminal retirement, rewrite replacement before index reset, and conflicting bytes. Task 4 must still prove receipt retries and bounded route behavior against this repaired store before Feature acceptance. Task 5's completed canonical Task record still has duplicate headings, `TBD` fields and a stale Parent Feature link; lifecycle guards prevented its Task owner from correcting it. The [exact correction handoff](../../feature_artifacts/feat_049_002_task5_record_correction.md) preserves the replacement text and refusal evidence for an authorized board path.

## Risks & upward questions

Consumer agreement was sent to epic_049 after comparing the completed producer and Task 4 fixtures; no mismatch found. Durable message IDs and reference publication remain this feature's responsibility. Chat write failure preserves source recovery evidence and repair admission. Monolithic ledger cost, disk exhaustion, ambiguous legacy replay and routing ambiguity remain measured/reported limits. No install or early child dispatch is requested.

## Decision log

None yet.

- `dec_001` · 2026-11-25 · Feature Lead · **API contracts**
  Chose Expose versioned transcript pages at GET /api/transcript/v1/<graph_id> with direction-bound incarnation/sequence cursors; retain a bounded legacy /api/chat/<graph_id> array with Link and explicit completeness headers..
  Rationale: The existing GET reads full JSONL and cannot support bounded refresh or older history. A separate versioned envelope gives deterministic pagination while preserving the established array consumer.
  Honors: Epic dec_005, success criteria 5–6, 50/100 rows, 1 MiB source, 256 KiB response, typed restart and read-only GET..

- `dec_006` · 2026-11-25 · Feature Lead · **Task breakdown**
  Chose Deliver the shared fenced JSONL/index boundary first, then receipt milestones and checkpoint-keyed replies, then immutable pages, HTTP compatibility and end-to-end crash acceptance..
  Rationale: Both source events and authored replies require the same cross-process append guarantee; bounded reads need committed offsets from both. This order keeps four reviewable slices and avoids a parallel scheduler or ledger.
  Honors: Epic dec_004–dec_006, selected crash matrix, Feature 1 consumer agreement and native C4 Code/design reconciliation..

- `dec_007` · 2026-11-25 · Feature Lead · **API contracts**
  Chose Use append_committed_recovery_receipt to return a durable receipt-to-message acknowledgement; after releasing the graph fence, record_transcript_milestone persists the publisher mapping and republishes aliases. Replay retries the same receipt key through a crash before acknowledgement..
  Rationale: The JSONL commit and producer progress index are separate durable stores. Stable receipt identity and replay preserve one line and ensure milestone_refs includes only committed transcript messages.
  Honors: Epic dec_004–dec_006; producer revision dc47068cebf5643c319d37785edf35882fb96941; source-lock release, graph fence, fsync, index commit, fence release and acknowledgement order..

- `dec_008` · 2026-11-25 · Feature Lead · **API contracts**
  Chose Expose oversized legacy message detail at GET /api/transcript/v1/<graph_id>/items/<message_id>/detail using immutable 64 KiB UTF-8 chunks and graph/incarnation/message/digest/offset-bound cursors..
  Rationale: A bounded preview preserves the legacy array and read budgets while allowing older large bodies to be retrieved without scanning authoritative JSONL on GET.
  Honors: Epic transcript read budget and typed restart contract; Feature 3 UI handoff requirement..

## Closeout

Completed child work: `task_049_002_001` (Build fenced durable transcript storage and room migration), `task_049_002_002` (Append deterministic recovery milestones from committed receipts), `task_049_002_003` (Give authored replies stable checkpoint identity), `task_049_002_004` (Expose bounded transcript pages and verify recovery history), `task_049_002_005` (Repair transcript replay durability and crash-safe room movement).
