# Recovery progress producer design

## Table of Contents

- [Purpose](#purpose)
- [Requirements](#requirements)
- [Decisions and Rationale](#decisions-and-rationale)
- [Interfaces](#interfaces)
- [Key Flows](#key-flows)
- [Architecture Links](#architecture-links)
- [Verification Evidence](#verification-evidence)
- [Child Designs and Directory Coverage](#child-designs-and-directory-coverage)

## Purpose

This directory owns the bounded producer that joins committed recovery receipts
to current execution evidence and publishes immutable, work-addressed progress
projections. It serves the [Watchdog](../watchdog/DESIGN.md) without owning
recovery authority, and supplies the read contract owned by the
[War Room](../war_room/DESIGN.md#recovery-summaries-and-planning-transcripts).
The War Room continues to own transcript durability, routing, movement and read
semantics.

## Requirements

### Functional Requirements

- `REQ-RECOVERY-PROGRESS-001` — A committed action or incident receipt projects
  its exact generation, attempt and claim against current live or postcheck
  evidence. Missing, expired, inaccessible, legacy or conflicting evidence is
  unavailable rather than proof of execution or verification.
- `REQ-RECOVERY-PROGRESS-002` — A transcript milestone mapping is inserted or
  refreshed only from the current, completely indexed source-key route while the
  owning graph fence remains held through the publisher SQLite commit. Receipt,
  entry, graph and message identities are immutable; pending transcript evidence
  leaves an existing mapping unchanged or a new mapping absent.
- `REQ-RECOVERY-PROGRESS-003` — Missed notifications and incomplete publication
  remain restart-replayable from authoritative ledgers, retained receipts and
  dirty aliases. Replay does not manufacture transcript routing or affect repair
  admission.

### Non-Functional Requirements

- `REQ-RECOVERY-PROGRESS-004` — One drain admits at most 100 receipts and 100
  dirty owners or one second. The best-effort fast path has a 250 ms deadline.
  Each entry point carries that single monotonic deadline through transcript
  append/deduplication, publisher and graph locks, and both SQLite stores; it
  does not start another blocking acquisition after exhaustion. Immutable pages
  retain explicit lag and completeness when work remains. Filesystem reads,
  appends and fsyncs already admitted under the deadline are not interruptible
  and are measured separately from bounded lock waits.

## Decisions and Rationale

- `DEC-RECOVERY-PROGRESS-001` — **Decision:** Keep a disposable, writer-only
  SQLite index for receipt deduplication, transcript mappings, aliases, dirty
  owners and fair replay cursors; publish immutable pages and atomically replace
  each work pointer. **Rationale:** Authoritative actions, incidents and
  transcripts remain in their owning stores while restart can cheaply rebuild
  the read projection. **Alternatives:** Making the projection authoritative or
  querying all ledgers during GET would couple recovery authority to presentation
  and make read cost unbounded.
- `DEC-RECOVERY-PROGRESS-002` — **Decision:** Every milestone writer acquires the
  process-local publisher lock and publisher SQLite write transaction before the
  transcript graph fence, then commits SQLite before releasing that fence.
  **Rationale:** The transcript index is the durable authority for current
  source-key routing; holding its fence across the second-store commit closes the
  delayed-acknowledgement check-to-write race without ordering opaque
  incarnations. **Alternatives:** A lookup before the transaction or a conditional
  refresh after releasing the fence permits a newer room route to be overwritten.

## Interfaces

| Source entry | Contract |
|---|---|
| [`publish_committed_transition`](publisher.py) | After the authoritative lifecycle commit, append or deduplicate the recovery transcript line, join its current fenced mapping and snapshot, then best-effort publish dirty aliases. |
| [`drain_recovery_progress`](publisher.py) | Fairly replay retained receipts and dirty aliases during startup and before slower Watchdog work, preserving the bounded cursor when evidence is pending. |
| [`record_transcript_milestone`](publisher.py) | Apply an already committed acknowledgement through the same fenced private mapping path and refresh existing entry references. |
| [`_record_transcript_milestone`](publisher.py) | Validate immutable acknowledgement identity and insert or refresh current incarnation and append sequence while the War Room source lookup keeps the graph fence held. |
| [`begin_live_observation`, `refresh_live_observation`, `end_live_observation`](live.py) | Retain process-generation-bound invocation and executor evidence used by projection; observations do not grant repair authority. |

The publisher SQLite file is
`.cascade/recovery_progress/v1/writer-index.sqlite3`. Its `receipts`, `entries`,
`aliases`, `dirty`, `transcript_milestones` and `meta` tables are disposable
projection state. Immutable manifests and pages live below
`.cascade/recovery_progress/v1/work/<sha256(work-id)>/`; `current.json` is the
atomic read pointer. The War Room's
[`fenced_transcript_source_acknowledgement`](../war_room/chat_store.py) either
yields current routing with the graph fence held or raises pending without
repair, import or projection work.

## Key Flows

```mermaid
sequenceDiagram
    participant L as Authoritative lifecycle ledger
    participant P as Recovery progress publisher
    participant W as War Room transcript/index
    participant I as Publisher SQLite
    participant F as Immutable progress pages
    L->>L: Commit receipt under lifecycle lock
    L-->>P: Notify after releasing source lock
    P->>W: Append/deduplicate recovery source key
    W-->>P: Durable acknowledgement after graph fence release
    P->>I: Publisher lock; BEGIN IMMEDIATE
    P->>W: Acquire graph fence; read current source-key route
    alt current and completely indexed
        P->>I: Insert/refresh mapping and entry references
        P->>I: Commit publisher transaction
        P-->>W: Release graph fence
        P->>F: Publish bounded dirty aliases
    else move, rewrite, append, import or room is pending
        W-->>P: Pending
        P->>I: Leave mapping absent/unchanged; retain replay eligibility
    end
```

A delayed acknowledgement cannot carry its saved incarnation into SQLite. Once
the publisher transaction begins, the private mapping helper rereads the source
key under the graph fence and uses that current route. Room rewrite or movement
must acquire the same fence, so it completes either before this lookup or after
the publisher commit. A genuine receipt/entry/graph/message conflict is refused.

On process restart, `drain_recovery_progress` scans the existing authoritative
ledgers from its retained fair cursor, deduplicates the recovery source key and
re-enters the same fenced mapping path. Missing or unfinished transcript state
keeps the receipt eligible for a later bounded pass; committed SQLite mappings
and dirty aliases resume publication without changing lifecycle admission.
Lock or SQLite contention likewise leaves the cursor at pending work and cannot
mint a mapping or discard the authoritative receipt.

## Architecture Links

- Source: [model.dsl](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl) and [views.dsl](../../architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/views.dsl)
- Rendered views: No separately checked-in Code render is authoritative; the
  local architecture browser renders the revision-pinned source above.
- Scope note: `cascade-watchdog-code` owns publisher entry points and the private
  mapping helper. `cascade-dashboard-code` owns the authoritative source lookup,
  graph fence and transcript index. Their native cross-view relationship records
  the publisher-to-transcript call; no extra deployment container is implied.

## Verification Evidence

| Requirement | Evidence | Status or gap |
|---|---|---|
| `REQ-RECOVERY-PROGRESS-001` | [publisher scenarios](../../tests/recovery_progress/test_publisher.py) | Verified for exact evidence joins, bounded publication, aliases and replay. |
| `REQ-RECOVERY-PROGRESS-002` | [milestone integration](../../tests/recovery_progress/test_transcript_milestones.py) and [transcript store](../../tests/war_room/test_durable_chat_store.py) | Verified for first insertion, delayed fast-path/drain/public writers, conflicts, pending state, room movement and current fenced routing. |
| `REQ-RECOVERY-PROGRESS-003` | [milestone restart/replay scenarios](../../tests/recovery_progress/test_transcript_milestones.py) | Verified for committed receipt replay and pending evidence without fabricated routing. |
| `REQ-RECOVERY-PROGRESS-004` | [publisher scenarios](../../tests/recovery_progress/test_publisher.py), [milestone integration](../../tests/recovery_progress/test_transcript_milestones.py) and [transcript store](../../tests/war_room/test_durable_chat_store.py) | Deterministic elapsed-time scenarios measure bounded publisher thread/SQLite and graph thread/process-fence contention, then verify replay completion. They do not establish a hard bound for already admitted filesystem opens, source reads, JSONL append or fsync. |

## Child Designs and Directory Coverage

This directory has no meaningful child subsystem. `__init__.py` is package
surface only; `live.py` and `publisher.py` are covered here because they
collaborate on the single progress-producer boundary.
