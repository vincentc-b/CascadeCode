---
id: epic_017
title: Prevent duplicate planning turns from queue cursor races
tier: epic
status: active
parent: null
children:
- feat_017_001
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

### Root cause (as observed in code at activation)

- `cascade/workspace/kickoff.py::deliver_queue_kickoffs` (watchdog thread, inside `deferred_kickoffs()`) calls each tier's `ingest_queue`, which does `graph.update_state(...)` to append event messages and set `last_queue_offset`. This runs **without** the per-graph `_graph_lock` that serializes `_run_kickoff`.
- A background turn already inside `graph.invoke` for the same thread works from its own in-memory channel values. Its next checkpoint supersedes the watchdog's `update_state` checkpoint, so **both the advanced `last_queue_offset` and the ingested event messages are lost** (the cursor is a last-value channel; the in-flight run never saw the write).
- `watchdog_tick` calls `_consume_explicit_events(force_work_queues=True)` every maintenance pass (~10s), so a regressed cursor re-reads the same lines and `kickoff_human_comment` / `queue_event` kickoffs are re-issued each pass. That is the loop.
- The same pattern exists for epic, feature, and task graphs because ingestion and kickoff share `kickoff.py`.

### Target design

1. **Single writer per graph.** Queue ingestion (read events -> append messages -> advance cursor) becomes part of the serialized per-graph job, executed under `_graph_lock(work_id)` on the same path as model turns. The watchdog never writes a graph checkpoint directly; it only detects "queue file is ahead of cursor" and submits a delivery job. Because ingest and `invoke` can no longer interleave, the checkpoint cursor is never overwritten by a stale in-flight run.
2. **Coalesced delivery.** At most one pending (not yet started) delivery job per graph. Repeated ticks while a job is pending or running are no-ops; the running job re-checks the queue after its turn so events that arrived mid-turn are picked up by exactly one follow-up. In-memory coalescing is only an optimization; correctness comes from the durable cursor read under the lock.
3. **One turn per delivered batch.** A batch is classified once: human `CommentPosted`/`CommentReplied` events are staged as human messages, non-comment lifecycle events as event messages, agent replies and `CommentResolved` are recorded but schedule nothing. The batch triggers at most one model turn, and only if it contained a human comment or a non-comment event.
4. **Monotonic cursor guard.** Cursor writes go through one helper that refuses to lower `last_queue_offset` (except the existing "queue file truncated/replaced" reset in `read_events`, which must be explicit and logged). Existing checkpoints and queue files are read unchanged, so no migration is needed and already-active graphs that are behind just catch up with one bounded delivery.
5. **Restart safety.** `resume_inflight_graphs` and queue delivery share the same serialized per-graph path. Resume re-checks `snapshot.next` under the lock, so an interrupted turn resumes at most once. The durable cursor, not in-memory state, decides what is new after restart.
6. **Targeted observability.** Log every delivery with `(work_id, cursor_before, cursor_after, queue_size, turn_started)`. Flag a graph whose queue size stays ahead of its cursor across consecutive maintenance passes while no turn is running, or that receives a kickoff for a batch ending at an offset it has already delivered. Emit one structured warning plus one War Room system note per incident, deduplicated per `(work_id, offset)`.

### Explicitly out of scope

- Changing the queue file format, LangGraph topology, or checkpointer backend.
- General watchdog performance work, retry policy, or model-capacity budgeting beyond the loop fix.
- New dashboards; observability is logs plus the existing War Room transcript.

## Cross-module constraints

- Preserve per-graph turn serialization and the watchdog's non-blocking supervision behavior.
- Do not drop human messages or non-comment lifecycle events.
- Keep queue files and existing checkpoints backward compatible; recovery must work for already-active graphs.
- Avoid relying only on in-memory deduplication because restarts must remain safe.
- Keep the fix focused on queue ingestion, cursor/checkpoint consistency, kickoff coalescing, and targeted observability.

## Core dependencies

- `cascade/workspace/kickoff.py`: `deliver_queue_kickoffs`, `kickoff_graph_queue_event`, `kickoff_human_comment`, `_classify_queue_events`, `_graph_lock`, `_submit_background`, `resume_inflight_graphs`.
- `cascade/{epic,feature,task}/graph.py`: `ingest_queue` (the cursor writer) and `ensure_*_graph`.
- `cascade/watchdog/loop.py`: `_consume_explicit_events` (forced on maintenance), `_resume_reclaimable_task_runs`.
- `cascade/watchdog/events.py`: `read_events` byte-offset semantics, including the reset when the offset is past EOF.
- `cascade/workspace/up.py`: boot-time `resume_inflight_graphs`.
- Existing tests to extend instead of duplicating: `tests/workspace/test_kickoff.py`, `tests/workspace/test_human_comment_kickoff.py`, `tests/watchdog/test_queue.py`, `tests/workspace/test_up.py`.

## Feature breakdown
- feat_017_001

1. **Serialized queue delivery and monotonic cursor** (`feat` minted at activation). Move ingestion under the per-graph lock and serial job path, coalesce delivery jobs, one turn per batch with the comment/agent/resolution classification above, a monotonic cursor helper for all three tiers. Regression tests: a queue append during an in-flight turn is ingested exactly once and the cursor ends at EOF; N maintenance ticks on an unchanged queue start zero turns; one human comment yields exactly one turn and one reply; agent reply / `CommentResolved` yields zero turns; event ordering in messages matches queue order. This feature alone stops the loop.
2. **Restart convergence and stall detection** (depends on 1). Route boot resume and watchdog delivery through the same serialized path so an interrupted turn resumes at most once, a behind-cursor graph from before the fix catches up in one bounded delivery and settles idle, and add the delivery log plus stalled-cursor / duplicate-kickoff warning. Tests: simulated restart with an interrupted checkpoint and pending queue lines (bounded invocations, idle at the end), plus a forced stall that emits exactly one warning.

Testing stance: prefer a small number of system-level tests with a fake planning-turn runner that counts invocations over per-function unit tests.

## Open questions

- Risk to retire first (feature 1, first task): write a failing reproduction that runs `ingest_queue` while a fake `graph.invoke` is blocked mid-node, and confirm the checkpoint after the turn has lost the advanced cursor and event messages. If LangGraph does not actually supersede the write, re-check the root cause before building.
- Does holding the per-graph lock during ingestion risk stalling the watchdog? Design answer: the watchdog only submits jobs (`deferred_kickoffs`), so it never waits on the lock; the architect should confirm no synchronous caller (for example `kickoff_graph_queue_event` outside `deferred_kickoffs`) would block.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-10-22 · epic_manager · Ingestion moves into the serialized per-graph job; the watchdog never writes graph checkpoints directly.
- 2026-10-22 · epic_manager · Two features: the core serialized delivery fix, then restart convergence plus stall detection. Observability is limited to logs and one War Room note.

- `dec_001` · 2026-10-22 · Epic Manager · **Macro-architecture**
  Chose Queue ingestion (read events, append messages, advance last_queue_offset) runs only inside the serialized per-graph kickoff job under _graph_lock; the watchdog only detects a queue ahead of the cursor and submits a coalesced delivery job..
  Rationale: The loop comes from an unlocked update_state in deliver_queue_kickoffs that an in-flight graph.invoke checkpoint supersedes, which loses the cursor and the event messages. Making a single writer per graph removes the race at its source and keeps restart safety, because the durable checkpoint cursor stays authoritative. A max-reducer alone would not help, since the in-flight run never sees the write.
  Honors: Success criteria: at-most-once incorporation, monotonic cursor; constraints: preserve per-graph serialization and non-blocking watchdog, no in-memory-only dedup, backward-compatible checkpoints.

- `dec_002` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose Two features: (1) serialized queue delivery and monotonic cursor with one turn per batch across all tiers; (2) restart convergence and stall/duplicate-kickoff detection, which depends on 1. Observability is limited to structured logs and one deduplicated War Room note per incident. Tests are a small set of system-level tests using a counting fake turn runner..
  Rationale: Feature 1 alone stops the loop and is the smallest shippable slice. Restart and observability build on the same serialized path, so they are sequenced after it. Dashboards and broader watchdog work are cut as scope creep.
  Honors: Cross-module constraint: keep the fix focused; frugal testing.
## Amendment log

_(none)_
