---
id: epic_017
title: Prevent duplicate planning turns from queue cursor races
tier: epic
status: active
parent: null
children:
- feat_017_001
- feat_017_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-22'
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Prevent duplicate planning turns from queue cursor races

## Intent

Planning graphs can repeatedly process the same queue events when queue ingestion races with an active model turn. The durable queue cursor may remain behind the queue file, causing each maintenance pass to enqueue another manager/architect cycle, repeat replies to an already-addressed human comment, consume unnecessary model capacity, and prevent the graph from converging to idle. Make queue consumption and planning-turn scheduling converge reliably during normal operation, concurrent comments, and supervisor restart.

### Success criteria

- Each queue event is incorporated into a graph at most once for scheduling purposes, including when a model turn is already running.
- The durable queue cursor advances monotonically and is not lost or overwritten by concurrent graph checkpoints.
- Repeated maintenance ticks with an unchanged queue do not start additional planning turns.
- Agent replies and comment-resolution events do not retrigger a planning turn; a new human comment or reply triggers exactly one authorized turn.
- After a supervisor restart, an interrupted turn resumes at most once and the graph settles to an idle checkpoint.
- Concurrent and restart-focused regression tests reproduce the former loop and verify bounded model invocations, cursor convergence, and preserved event ordering.
- Operational visibility identifies a non-advancing cursor or duplicate kickoff before it becomes an unbounded loop.

## Macro-architecture

### Root cause (as observed in code at activation; confirmed by architect spike)

- `cascade/workspace/kickoff.py::deliver_queue_kickoffs` (watchdog thread, inside `deferred_kickoffs()`) calls each tier's `ingest_queue`, which does `graph.update_state(...)` to append event messages and set `last_queue_offset`. This runs **without** the per-graph `_graph_lock` that serializes `_run_kickoff`.
- A background turn already inside `graph.invoke` for the same thread works from its own in-memory channel values. Its next checkpoint supersedes the watchdog's `update_state` checkpoint, so **both the advanced `last_queue_offset` and the ingested event messages are lost** (the cursor is a last-value channel; the in-flight run never saw the write).
- **Confirmed** against the installed langgraph 1.2.14 + `SqliteSaver`: with a node blocked mid-turn, a concurrent `update_state` set the cursor to 120 and appended an event message (visible mid-turn); after the node returned, the latest checkpoint had cursor 0 and no event message. The root cause stands; feat_017_001's first test is now a regression test, not a go/no-go gate.
- `watchdog_tick` calls `_consume_explicit_events(force_work_queues=True)` every maintenance pass (~10s), so a regressed cursor re-reads the same lines and `kickoff_human_comment` / `queue_event` kickoffs are re-issued each pass. That is the loop.
- The same pattern exists for epic, feature, and task graphs because ingestion and kickoff share `kickoff.py`.
- **Other unlocked cursor writers (architect review):** the dispatch boot hooks `cascade/{epic,feature,task}/boot.py` call `ingest_queue` (and `seed_*_role_models`) directly from `_boot_after` in `cascade/watchdog/dispatch.py`, outside `_graph_lock`. Today's batch handling also fans out: every human comment in a batch gets its own `kickoff_human_comment` turn, plus one more `queue_event` turn if any non-comment event is present.

### Target design

1. **Single writer per graph.** Queue ingestion (read events -> append messages -> advance cursor) becomes part of the serialized per-graph job, executed under `_graph_lock(work_id)` on the same path as model turns. The watchdog never writes a graph checkpoint directly; it only detects "queue file is ahead of cursor" and submits a delivery job. Because ingest and `invoke` can no longer interleave, the checkpoint cursor is never overwritten by a stale in-flight run.
   - Concretely: one locked delivery step in `kickoff.py` is the **only** caller of tier `ingest_queue`. Every serialized job (`activate`, `dispatch`, `queue_event`, `comment`, `human_message`) runs that step first, before deciding whether to invoke. The boot hooks stop calling `ingest_queue`; the `activate`/`dispatch` job that `_boot_after` already submits does the ingestion under the lock.
   - **Exempt: `invoke_tool`** (`cascade/{epic,feature}/graph.py`) appends tool messages during a turn from the Cursor SDK tool callback (or the MCP stdio process for CLI providers) while the turn's job holds `_graph_lock`. It must **not** take the lock, because that would deadlock against the turn it serves. It never writes the cursor, so it is outside this fix. Any lost tool messages are a separate issue.
2. **Coalesced delivery.** At most one pending (not yet started) delivery job per graph. Repeated ticks while a job is pending or running are no-ops; the running job re-checks the queue after its turn so events that arrived mid-turn are picked up by exactly one follow-up. In-memory coalescing is only an optimization; correctness comes from the durable cursor read under the lock.
   - The follow-up re-check is a loop **inside** the running job. It must not call `kickoff_turn`, because `_defer_turns` is a contextvar that the `kickoff-{work_id}` drain thread does not inherit, so a nested `kickoff_turn` would run synchronously and recurse.
3. **One turn per delivered batch.** A batch is classified once: human `CommentPosted`/`CommentReplied` events are staged as human messages, non-comment lifecycle events as event messages, agent replies and `CommentResolved` are recorded but schedule nothing. The batch triggers at most one model turn, and only if it contained a human comment or a non-comment event.
   - Comment staging reuses `_comment_kickoff_content` and the existing eligibility checks in `kickoff_human_comment` (author is human, the doc is in `2_active`, the tier is epic or feature). Several human comments in one batch become several human messages but only one turn.
4. **Monotonic cursor guard.** Cursor writes go through one helper that refuses to lower `last_queue_offset`. The only exception is a queue file that was truncated or replaced, which must be handled explicitly and logged. Today `events._decode_buffer` silently restarts from 0 when the offset is past EOF, and `read_events` returns `([], 0)` when the file is missing. The helper treats "cursor > current file size" as that explicit, logged reset. `read_events` keeps its signature. A file replaced by a larger one can't be detected without storing file identity, which would change the checkpoint schema; that limitation is accepted and pre-existing. Existing checkpoints and queue files are read unchanged, so no migration is needed and already-active graphs that are behind just catch up with one bounded delivery.
5. **Restart safety.** `resume_inflight_graphs` and queue delivery share the same serialized per-graph path. Resume re-checks `snapshot.next` under the lock, so an interrupted turn resumes at most once. The durable cursor, not in-memory state, decides what is new after restart.
   - **Ordering:** when `snapshot.next` is non-empty, the job resumes **before** it ingests. Calling `update_state` on an interrupted checkpoint can change `next` and silently drop the resume. Queue lines that arrived meanwhile are delivered by the post-turn re-check, in one follow-up at most.
6. **Targeted observability.** Log every delivery with `(work_id, cursor_before, cursor_after, queue_size, turn_started)`. Flag a graph whose queue size stays ahead of its cursor across consecutive maintenance passes while no turn is running, or that receives a kickoff for a batch ending at an offset it has already delivered. Emit one structured warning plus one War Room system note per incident, deduplicated per `(work_id, offset)`.

### Explicitly out of scope

- Changing the queue file format, LangGraph topology, or checkpointer backend.
- General watchdog performance work, retry policy, or model-capacity budgeting beyond the loop fix.
- New dashboards; observability is logs plus the existing War Room transcript.
- Tool messages from `invoke_tool` written during a turn (same overwrite class, but they don't affect the cursor or scheduling).

## Cross-module constraints

- Preserve per-graph turn serialization and the watchdog's non-blocking supervision behavior.
- The watchdog thread never holds or waits on a `_graph_lock`. Watchdog paths that dispatch work must run inside `deferred_kickoffs()`. Today `advance_work` in `watchdog_tick` and the boss order consumer (`tick_boss_consumer`, which also holds `process_lock`) call `dispatch_*` -> `_boot_after` -> `kickoff_turn` *synchronously*, which runs a full model turn on the watchdog thread.
- `invoke_tool` and any other code reachable from inside a running turn must not acquire `_graph_lock`.
- Do not drop human messages or non-comment lifecycle events.
- Keep queue files and existing checkpoints backward compatible; recovery must work for already-active graphs.
- Avoid relying only on in-memory deduplication because restarts must remain safe.
- Keep the fix focused on queue ingestion, cursor/checkpoint consistency, kickoff coalescing, and targeted observability.

## Core dependencies

- `cascade/workspace/kickoff.py`: `deliver_queue_kickoffs`, `kickoff_graph_queue_event`, `kickoff_human_comment`, `_classify_queue_events`, `_graph_lock`, `_submit_background`, `resume_inflight_graphs`.
- `cascade/{epic,feature,task}/graph.py`: `ingest_queue` (the cursor writer) and `ensure_*_graph`; `invoke_tool` (must stay lock-free).
- `cascade/{epic,feature,task}/boot.py`: drop the direct `ingest_queue` call.
- `cascade/watchdog/dispatch.py`: `_boot_after` (boot hooks plus the activate/dispatch kickoff).
- `cascade/watchdog/loop.py`: `_consume_explicit_events` (forced on maintenance), `_resume_reclaimable_task_runs`, `watchdog_tick` -> `advance_work` (wrap in `deferred_kickoffs`).
- `cascade/boss/graph.py` / `cascade/boss/orders.py`: order-driven `dispatch_*` (wrap in `deferred_kickoffs`).
- `cascade/watchdog/events.py`: `read_events` / `_decode_buffer` byte-offset semantics, including the silent reset when the offset is past EOF.
- `cascade/workspace/up.py`: boot-time `resume_inflight_graphs`.
- Existing tests to extend instead of duplicating: `tests/workspace/test_kickoff.py`, `tests/workspace/test_human_comment_kickoff.py`, `tests/watchdog/test_queue.py`, `tests/workspace/test_up.py`, `tests/watchdog/test_watchdog.py`. That last file monkeypatches `deliver_queue_kickoffs` and `kickoff_graph_queue_event` by name, so keep those entry points.

## Feature breakdown
- feat_017_001
- feat_017_002

1. **feat_017_001 · Serialized queue delivery and monotonic cursor.** Move ingestion under the per-graph lock and serial job path, as the first step of every job (boot hooks included), coalesce delivery jobs, one turn per batch with the comment/agent/resolution classification above, a monotonic cursor helper for all three tiers. Run the watchdog `advance_work` and boss-order dispatch paths inside `deferred_kickoffs()`. Regression tests: a queue append during an in-flight turn is ingested exactly once and the cursor ends at EOF (this reproduces the confirmed overwrite); N maintenance ticks on an unchanged queue start zero turns; one human comment yields exactly one turn and one reply, and two in the same batch also yield one turn; agent reply / `CommentResolved` yields zero turns; event ordering in messages matches queue order. This feature alone stops the loop.
2. **feat_017_002 · Restart convergence and stall detection** (depends on feat_017_001). Route boot resume and watchdog delivery through the same serialized path so an interrupted turn resumes at most once (resume before ingest), a behind-cursor graph from before the fix catches up in one bounded delivery and settles idle, and add the delivery log plus stalled-cursor / duplicate-kickoff warning. Tests: simulated restart with an interrupted checkpoint and pending queue lines (bounded invocations, idle at the end), plus a forced stall that emits exactly one warning.

Testing stance: prefer a small number of system-level tests with a fake planning-turn runner that counts invocations over per-function unit tests. Use a real `SqliteSaver` in these tests (not a mocked graph), because the bug lives in checkpoint semantics.

## Open questions

- **Resolved: does LangGraph supersede the watchdog's write?** Yes. The architect spike reproduced it on langgraph 1.2.14 with `SqliteSaver`: the cursor went from 120 back to 0 and the event message was lost. See Root cause.
- **Resolved: would holding the per-graph lock during ingestion stall the watchdog?** `kickoff_graph_queue_event` has one production caller, `_resume_reclaimable_task_runs`, and it already runs inside `deferred_kickoffs()`, so it does not block. The real synchronous lock holders are the dispatch paths (`advance_work`, the boss order consumer), which run `kickoff_turn` inline on the watchdog thread. Those graphs are freshly dispatched with no running job, so ingestion won't contend, but the spec now requires wrapping those paths in `deferred_kickoffs()` to keep the watchdog submit-only. Two deadlock risks are also ruled out by constraint: `invoke_tool` stays lock-free, and follow-ups are a loop inside the job rather than a nested `kickoff_turn`.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-22 · Epic Manager · **Macro-architecture**
  Chose Queue ingestion (read events, append messages, advance last_queue_offset) runs only inside the serialized per-graph kickoff job under _graph_lock; the watchdog only detects a queue ahead of the cursor and submits a coalesced delivery job..
  Rationale: The loop comes from an unlocked update_state in deliver_queue_kickoffs that an in-flight graph.invoke checkpoint supersedes, which loses the cursor and the event messages. Making a single writer per graph removes the race at its source and keeps restart safety, because the durable checkpoint cursor stays authoritative. A max-reducer alone would not help, since the in-flight run never sees the write.
  Honors: Success criteria: at-most-once incorporation, monotonic cursor; constraints: preserve per-graph serialization and non-blocking watchdog, no in-memory-only dedup, backward-compatible checkpoints.

- `dec_002` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose Two features: (1) serialized queue delivery and monotonic cursor with one turn per batch across all tiers; (2) restart convergence and stall/duplicate-kickoff detection, which depends on 1. Observability is limited to structured logs and one deduplicated War Room note per incident. Tests are a small set of system-level tests using a counting fake turn runner..
  Rationale: Feature 1 alone stops the loop and is the smallest shippable slice. Restart and observability build on the same serialized path, so they are sequenced after it. Dashboards and broader watchdog work are cut as scope creep.
  Honors: Cross-module constraint: keep the fix focused; frugal testing.

- `dec_003` · 2026-10-22 · Epic Architect · **Macro-architecture**
  Chose Root cause confirmed. One locked delivery step in kickoff.py is the only caller of tier ingest_queue and runs first in every serialized job. The boot hooks stop calling ingest_queue. invoke_tool is explicitly kept lock-free..
  Rationale: A spike on langgraph 1.2.14 with SqliteSaver showed an in-flight invoke checkpoint resetting the cursor from 120 to 0 and dropping the event message. The boot hooks in {epic,feature,task}/boot.py were a second unlocked cursor writer that dec_001 did not cover. invoke_tool runs on the SDK tool callback or MCP process while the turn's job holds the lock, so taking the lock there would deadlock, and it never writes the cursor.
  Honors: Success criteria: at-most-once incorporation, monotonic cursor. Constraint: preserve per-graph serialization..

- `dec_004` · 2026-10-22 · Epic Architect · **Cross-module constraints**
  Chose The watchdog's advance_work and boss-order dispatch paths run inside deferred_kickoffs(). The post-turn queue re-check is a loop inside the running job, not a nested kickoff_turn..
  Rationale: kickoff_graph_queue_event's only production caller is already deferred, so it doesn't block. But dispatch_* -> _boot_after -> kickoff_turn currently runs model turns synchronously on the watchdog thread, and in the boss path it does so while holding process_lock, which contradicts the premise that the watchdog only submits jobs. The fix is one wrapper per call site. _defer_turns is a contextvar that the drain thread does not inherit, so a nested kickoff_turn inside a job would run synchronously and recurse.
  Honors: Constraint: the watchdog stays non-blocking. Keep the fix focused (wrapping call sites only, no new watchdog work)..
## Amendment log

_(none)_
