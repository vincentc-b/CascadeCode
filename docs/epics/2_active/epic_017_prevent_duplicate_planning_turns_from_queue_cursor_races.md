---
id: epic_017
title: Prevent duplicate planning turns from queue cursor races
tier: epic
status: active
parent: null
children:
- feat_017_001
- feat_017_002
- feat_017_003
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
plan_approved_at: '2026-10-22T22:14:48.630705+00:00'
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
   - Concretely: one locked delivery step in `kickoff.py` is the **only** caller of tier `ingest_queue`. Every serialized job (`activate`, `dispatch`, `queue_event`, `comment`, `human_message`) runs that step at the start, before deciding whether to invoke, **except** when the graph has an interrupted turn (as defined in item 5): then the job resumes first and performs ingestion and any other state writes afterwards. The boot hooks stop calling `ingest_queue`; the `activate`/`dispatch` job that `_boot_after` already submits does the ingestion under the lock.
   - **Exempt: `invoke_tool`** (`cascade/{epic,feature}/graph.py`) appends tool messages during a turn from the Cursor SDK tool callback (or the MCP stdio process for CLI providers) while the turn's job holds `_graph_lock`. It must **not** take the lock, because that would deadlock against the turn it serves. It never writes the cursor, so it is outside this fix. Any lost tool messages are a separate issue.
2. **Coalesced delivery.** At most one pending (not yet started) delivery job per graph. Repeated ticks while a job is pending or running are no-ops; the running job re-checks the queue after its turn so events that arrived mid-turn are picked up by exactly one follow-up. In-memory coalescing is only an optimization; correctness comes from the durable cursor read under the lock.
   - The follow-up re-check is a bounded loop **inside** the running job. `_defer_turns` is a contextvar that the `kickoff-{work_id}` drain thread does not inherit, so a `kickoff_turn` called inside the job runs synchronously under the re-entrant `_graph_lock`. That is allowed, provided the called path never schedules another delivery job (no recursion). Lines still pending when the loop bound is reached are picked up by the next maintenance pass.
3. **One turn per delivered batch.** A batch is classified once: human `CommentPosted`/`CommentReplied` events are staged as human messages, non-comment lifecycle events as event messages, agent replies and `CommentResolved` are recorded but schedule nothing. The batch triggers at most one model turn, and only if it contained a human comment or a non-comment event.
   - Comment staging reuses `_comment_kickoff_content` and the existing eligibility checks in `kickoff_human_comment` (author is human, the doc is in `2_active`, the tier is epic or feature). Several human comments in one batch become several human messages but only one turn.
4. **Monotonic cursor guard.** Cursor writes go through one helper that refuses to lower `last_queue_offset`. The only exception is a queue file that was truncated or replaced, which must be handled explicitly and logged. Today `events._decode_buffer` silently restarts from 0 when the offset is past EOF, and `read_events` returns `([], 0)` when the file is missing. The helper treats "cursor > current file size" as that explicit, logged reset. `read_events` keeps its signature. A file replaced by a larger one can't be detected without storing file identity, which would change the checkpoint schema; that limitation is accepted and pre-existing. Existing checkpoints and queue files are read unchanged, so no migration is needed and already-active graphs that are behind just catch up with one bounded delivery.
5. **Restart safety.** `resume_inflight_graphs` and queue delivery share the same serialized per-graph path. Resume re-checks for an interrupted turn under the lock, so an interrupted turn resumes at most once. The durable cursor, not in-memory state, decides what is new after restart.
   - **Interrupted** means `_graph_has_inflight_turn` is true: `snapshot.next` is non-empty **and** the thread already holds at least one role message (`epic_manager`/`epic_architect`, `feature_lead`/`feature_architect`, or `swe`). `snapshot.next` alone is not enough. An architect spike on langgraph 1.2.14 + `SqliteSaver` showed that `update_state` on a thread with no completed run leaves `next` at the entry node, so a freshly seeded or ingested graph would look interrupted. On a thread that has completed a run, an idle `update_state` leaves `next` empty. No graph uses LangGraph `interrupt()`/`interrupt_before`/`interrupt_after`, so with this definition an interrupted graph is always a turn cut off partway, and resuming it first is correct.
   - **Accepted gap:** a graph's very first turn that is cut off before it writes any role message is not auto-resumed at boot. Its pending entry node survives later state writes, and the next delivery or comment job runs the turn.
   - **Ordering:** when the graph has an interrupted turn, the job resumes **before** any `update_state` on that thread: ingestion, and also the `_stage_human_message` write that `comment`/`human_message` jobs do today. Such a job finishes the resumed turn, then stages its message and runs its own turn as usual. Neither the message nor the resume is lost. Calling `update_state` on an interrupted checkpoint can change `next` and silently drop the resume. Queue lines that arrived meanwhile are delivered by the post-turn re-check, in one follow-up at most. This rule is part of the job step defined in item 1. feat_017_001 shipped the ingestion half; the `_stage_human_message` half ships in feat_017_003 (dec_011). feat_017_002 routes boot resume through it and proves restart convergence.
6. **Targeted observability.** Log every delivery with `(work_id, cursor_before, cursor_after, queue_size, turn_started)`. Flag a graph whose queue size stays ahead of its cursor across consecutive maintenance passes while no turn is running, or that receives a kickoff for a batch ending at an offset it has already delivered. Emit one structured warning plus one War Room system note per incident, deduplicated per `(work_id, offset)`.

### Explicitly out of scope

- Changing the queue file format, LangGraph topology, or checkpointer backend.
- General watchdog performance work, retry policy, or model-capacity budgeting beyond the loop fix.
- New dashboards; observability is logs plus the existing War Room transcript.
- Tool messages from `invoke_tool` written during a turn (same overwrite class, but they don't affect the cursor or scheduling).
- The boot hooks' `seed_*_role_models` write stays in the hook, outside the lock. It never writes the cursor, except to 0 on an empty checkpoint, and it runs only on a dispatch transition (backlog/ready_to_plan to active, or a blocked task restart), when no turn is running. Moving it would change how models are refreshed on restart, because the job-side `_ensure_role_models` skips seeding when models already exist.

## Cross-module constraints

- Preserve per-graph turn serialization and the watchdog's non-blocking supervision behavior.
- The watchdog thread never holds or waits on a `_graph_lock`. Watchdog paths that dispatch work must run inside `deferred_kickoffs()`. Today `advance_work` in `watchdog_tick` and the boss order consumer (`tick_boss_consumer`, which also holds `process_lock`) call `dispatch_*` -> `_boot_after` -> `kickoff_turn` *synchronously*, which runs a full model turn on the watchdog thread.
- `invoke_tool` and any other code reachable from inside a running turn must not acquire `_graph_lock`.
- Do not drop human messages or non-comment lifecycle events.
- Keep queue files and existing checkpoints backward compatible; recovery must work for already-active graphs.
- Avoid relying only on in-memory deduplication because restarts must remain safe.
- Keep the fix focused on queue ingestion, cursor/checkpoint consistency, kickoff coalescing, and targeted observability.

## Core dependencies

- `cascade/workspace/kickoff.py`: `deliver_queue_kickoffs`, `kickoff_graph_queue_event`, `kickoff_human_comment`, `_classify_queue_events`, `_graph_lock`, `_submit_background`, `resume_inflight_graphs`, `_graph_has_inflight_turn` (the single definition of an interrupted turn).
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
- feat_017_003

**Source of truth:** the feat_017_001 and feat_017_002 stubs were minted before the architect review (dec_003–dec_007). Where a stub and this section differ, this section wins; feature leads fold these items into their spec when they start. The feat_017_003 stub was minted after the review (dec_011) and already matches this section, except that its "merge before feat_017_002 starts" sequencing note is superseded by item 2 below.

**Epic acceptance gate for feat_017_001 (dec_009, revised by dec_011):** gate items were (a) the boot hooks no longer call `ingest_queue`; (b) `advance_work` and the boss-order dispatch run inside `deferred_kickoffs()`; (c) resume before any state write when the graph has an interrupted turn (`_graph_has_inflight_turn`), including `_stage_human_message`, with the comment-on-interrupted-checkpoint test; (d) two human comments in one batch start exactly one turn; (e) the post-turn re-check is a bounded loop inside the job; (f) tests use a real `SqliteSaver`. feat_017_001 closed without a follow-up task for (b) and (c), so those two items moved to feat_017_003. feat_017_001 is accepted at epic review on (a), (d), (e) and (f) alone and is not reopened.

**Gate status (dec_011), checked against the feat_017_001 branch after `task_017_001_004` merged (`e844530`) and the feature doc moved to `3_completed` (`5dcc39c`):** (a), (d) and (e) are met: the boot hooks dropped `ingest_queue`; `_run_queue_delivery_locked` stages a whole batch via `_staged_messages_from_queue_events` and calls `kickoff_turn` once per batch inside a two-pass loop under the lock. (f) appears met: the feature tests use the real graphs via `tests/harness/queue_delivery.py`. Still open and owned by feat_017_003: (b) `advance_work` in `cascade/watchdog/loop.py` and the `dispatch_*` calls in `cascade/boss/orders.py` are not wrapped in `deferred_kickoffs()`; (c) `_kickoff_turn` skips ingestion on an interrupted graph but still calls `_stage_human_message` before resuming on `comment`/`human_message` jobs, and no test covers a comment landing on an interrupted checkpoint.

1. **feat_017_001 · Serialized queue delivery and monotonic cursor** (completed in its worktree). Ingestion under the per-graph lock as the start of every job (boot hooks included), skipped on an interrupted graph. Coalesced delivery with the post-turn re-check as a bounded loop inside the job. One turn per batch with the comment/agent/resolution classification above. A monotonic cursor helper for all three tiers, with the logged past-EOF reset. Regression tests: a queue append during an in-flight turn is ingested exactly once and the cursor ends at EOF (this reproduces the confirmed overwrite); N maintenance ticks on an unchanged queue start zero turns; one human comment yields exactly one turn and one reply, and two in the same batch also yield one turn; agent reply / `CommentResolved` yields zero turns; event ordering in messages matches queue order. This feature alone stops the loop.
2. **feat_017_002 · Restart convergence and stall detection** (depends on feat_017_001; already active, `task_017_002_001` in progress). Route boot `resume_inflight_graphs` through the same serialized path so an interrupted turn resumes at most once, confirm a behind-cursor graph from before the fix catches up in one bounded delivery and settles idle, and add the delivery log plus stalled-cursor / duplicate-kickoff warning. "Interrupted" means `_graph_has_inflight_turn` (dec_010), not `snapshot.next` alone; the restart test's interrupted checkpoint must hold a role message. Tests: simulated restart with an interrupted checkpoint and pending queue lines (bounded invocations, idle at the end), plus a forced stall that emits exactly one warning. It does not wait for feat_017_003: its boot resume uses the `resume_inflight` job, which ingests after resuming and never stages a human message, so it does not need gate item (c). **Actual order (dec_013):** feat_017_003 cannot dispatch while feat_017_002 is in `2_active`, because `epic_blocks_feature_dispatch` (evaluated on `merged_board`, which includes worktree docs) blocks any sibling dispatch while another feature of the epic is active. So feat_017_002 completes first and feat_017_003 follows. feat_017_003's only predecessor is feat_017_001, so it is based on feat_017_001's branch (or the epic branch once that review closes), not on feat_017_002's; both edit `_kickoff_turn`, so feat_017_003 rebases onto feat_017_002's changes before it merges.
3. **feat_017_003 · Submit-only watchdog dispatch and resume-before-stage guard** (depends on feat_017_001; dispatches after feat_017_002 leaves `2_active`, see item 2). Gate items (b) and (c): wrap `advance_work` and the boss-order `dispatch_*` calls in `deferred_kickoffs()`; in `_kickoff_turn`, when `_graph_has_inflight_turn` is true, resume the cut-off turn before `_stage_human_message`, then stage and run the job's own turn. Tests: extend the existing `SqliteSaver` scenario file so a `comment` job landing on an interrupted checkpoint resumes the cut-off turn once, then runs exactly one more turn with the message preserved; and one check that `watchdog_tick` dispatching work does not run a model turn on the calling thread.

Testing stance: prefer a small number of system-level tests with a fake planning-turn runner that counts invocations over per-function unit tests. Use a real `SqliteSaver` in these tests (not a mocked graph), because the bug lives in checkpoint semantics.

## Open questions

- **Resolved: does LangGraph supersede the watchdog's write?** Yes. The architect spike reproduced it on langgraph 1.2.14 with `SqliteSaver`: the cursor went from 120 back to 0 and the event message was lost. See Root cause.
- **Resolved: would holding the per-graph lock during ingestion stall the watchdog?** `kickoff_graph_queue_event` has one production caller, `_resume_reclaimable_task_runs`, and it already runs inside `deferred_kickoffs()`, so it does not block. The real synchronous lock holders are the dispatch paths (`advance_work`, the boss order consumer), which run `kickoff_turn` inline on the watchdog thread. Those graphs are freshly dispatched with no running job, so ingestion won't contend, but the spec now requires wrapping those paths in `deferred_kickoffs()` to keep the watchdog submit-only. Two deadlock risks are also ruled out by constraint: `invoke_tool` stays lock-free, and follow-ups are a bounded loop inside the job that never schedules another delivery.
- **Resolved: is a non-empty `snapshot.next` always an interrupted turn?** No. On a thread with no completed run it is set by any `update_state`. The interrupted-turn test is `_graph_has_inflight_turn` (non-empty `next` plus a role message); see Target design item 5.

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

- `dec_005` · 2026-10-22 · Epic Architect · **Macro-architecture**
  Chose When snapshot.next is non-empty, the job resumes before it ingests. The monotonic cursor helper treats cursor > current file size as the only allowed explicit, logged reset. read_events keeps its signature, and no file identity is stored..
  Rationale: Calling update_state on an interrupted checkpoint can change next and silently drop the resume. _decode_buffer already restarts from 0 when the offset is past EOF, so making that case explicit is enough. Detecting a file replaced by a larger one would need a checkpoint schema change, which is out of scope; that limitation is accepted as pre-existing.
  Honors: Success criteria: an interrupted turn resumes at most once, monotonic cursor. Constraints: backward-compatible checkpoints and queue format..

- `dec_006` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose The resume-before-ingest rule (dec_005) ships in feat_017_001 as part of the locked job step, not in feat_017_002. feat_017_002 keeps routing boot resume through that path, the restart convergence test, and observability. The epic's feature breakdown supersedes the pre-review feature stubs. The feat_017_001 regression assertions may share a few scenario tests..
  Rationale: feat_017_001 makes ingest the first step of every serialized job. Without the guard, any job that lands on an interrupted checkpoint would ingest first and could silently drop the resume, so feat_017_001 would ship a known regression until feat_017_002 landed. The guard is a single snapshot.next check, so moving it adds almost no scope. The stubs were minted before dec_003-dec_005 and lack the boot-hook, deferred_kickoffs, and two-comments-one-turn requirements.
  Honors: Success criteria: an interrupted turn resumes at most once; feat_017_001 is the smallest shippable slice that is safe on its own; frugal testing..

- `dec_007` · 2026-10-22 · Epic Architect · **Macro-architecture**
  Chose Widen dec_005/dec_006: on an interrupted checkpoint (snapshot.next non-empty) the job resumes before any update_state, which covers both ingest_queue and the _stage_human_message write in comment/human_message jobs. Those jobs stage their message and run their own turn after the resumed turn finishes. The boot hooks' seed_*_role_models write stays outside the lock and is listed as out of scope..
  Rationale: The hazard is any update_state on an interrupted checkpoint, not ingest specifically. _stage_human_message in _kickoff_turn writes state before the turn, so with only ingest guarded, a comment arriving after a crash could still drop the resume. The code has no LangGraph interrupt()/interrupt_before/interrupt_after, and _graph_has_inflight_turn is the only reader of snapshot.next, so a non-empty next always means a turn cut off partway and resuming first is always correct. seed_*_role_models never writes the cursor except to 0 on an empty checkpoint, and it runs only on dispatch transitions with no turn running. Moving it would change how models are refreshed, because _ensure_role_models skips seeding when models already exist.
  Honors: Success criteria: an interrupted turn resumes at most once; human messages are not dropped. Constraint: keep the fix focused (same single snapshot.next guard, no new writer moved)..

- `dec_008` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose Accept dec_007. feat_017_001's regression assertions gain one more: a comment job that lands on an interrupted checkpoint resumes the cut-off turn once, then stages its message and runs exactly one more turn. It folds into the existing shared scenario tests, so no new test file is added. The source-of-truth note now covers dec_003 through dec_007..
  Rationale: dec_007 widened the resume-first guard to the _stage_human_message write, but no listed test exercised that path. feat_017_002's restart test only covers pending queue lines. The guard ships in feat_017_001, so its proof should ship there too. Otherwise the comment path stays unverified until feat_017_002 lands. It is a single assertion against the same SqliteSaver fixture, so it costs almost nothing.
  Honors: Success criteria: an interrupted turn resumes at most once; human messages are not dropped. Frugal testing: extend shared scenarios rather than add per-function tests..

- `dec_009` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose feat_017_001 is not accepted at epic review until the post-review items are merged: boot hooks stop calling ingest_queue; advance_work and boss-order dispatch run inside deferred_kickoffs(); resume before any state write on an interrupted checkpoint (with the comment-job test); two comments in one batch start one turn; post-turn re-check is a loop in the job; tests use a real SqliteSaver. The lead may amend the active task_017_001_003 or add a follow-up task inside feat_017_001. No new feature is minted..
  Rationale: task_017_001_003 went active from the pre-review stub, so the no-rework window closed. Merged as written, feat_017_001 would leave an unlocked cursor writer, inline model turns on the watchdog thread (one under process_lock), and a dropped-resume hazard, and feat_017_002 depends on the resume guard and single ingestion path. Minting a separate feature would split one locked job step across two owners and risk duplicate work, so the fix stays inside feat_017_001 with either delivery route allowed.
  Honors: Success criteria: at-most-once incorporation, monotonic cursor, interrupted turn resumes at most once. Constraint: watchdog stays non-blocking. Smallest change: no new feature..

- `dec_010` · 2026-10-22 · Epic Architect · **Macro-architecture**
  Chose Correct dec_007: an interrupted turn is defined by _graph_has_inflight_turn (snapshot.next non-empty AND the thread holds a role message), not by snapshot.next alone; all resume-first rules and gate item (c) use that definition. A kickoff_turn called synchronously inside the delivery job is allowed if it never schedules another delivery, and the re-check loop may be bounded. Gate status after task_017_001_003 merged (fa3bac9): (a), (e) met, (f) appears met; (b), (c), (d) open, with (d) in task_017_001_004 and (b)/(c) needing a follow-up task inside feat_017_001..
  Rationale: A spike on langgraph 1.2.14 + SqliteSaver showed update_state on a thread with no completed run leaves next at the entry node, so dec_007's claim that a non-empty next always means a cut-off turn was wrong for freshly seeded or ingested graphs; the merged code's narrowed check fixes that and an idle update_state after a completed run leaves next empty. The residual gap (a first-ever turn cut off before any role message is not auto-resumed at boot) is harmless because its pending entry node survives and the next job runs it. The nested synchronous kickoff_turn in the merged loop runs under the re-entrant lock and does not recurse, so rejecting it at review would be ceremony. The merged comment path still stages a human message before resuming, and advance_work/boss dispatch are still unwrapped, so those gate items stay open.
  Honors: Success criteria: an interrupted turn resumes at most once; human messages are not dropped. Constraint: watchdog stays non-blocking. Smallest change: accept the lead's correct deviation instead of reworking merged code..

- `dec_011` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose Supersede dec_009's 'no new feature' clause. feat_017_001 closed (task_017_001_004 merged e844530, doc in 3_completed at 5dcc39c) with gate items (a), (d), (e), (f) met and no follow-up task for (b) and (c). Mint feat_017_003 (depends on feat_017_001) to own (b) wrapping advance_work and boss-order dispatch_* in deferred_kickoffs(), and (c) resuming an interrupted turn (_graph_has_inflight_turn) before _stage_human_message, with the comment-on-interrupted-checkpoint SqliteSaver test. feat_017_001 is accepted at epic review on (a), (d), (e), (f) and is not reopened. feat_017_002 should start after feat_017_003 merges..
  Rationale: dec_009 avoided a new feature to keep one locked job step under one owner while feat_017_001 was in flight. That premise is gone: feat_017_001 is closed and nobody owns (b)/(c). Reopening a completed feature is rework and ceremony; a human handoff comment was requested for many turns and never arrived. A minted stub is the only channel the epic team controls that reaches a feature lead, so the requirements now travel with the work. The scope is two call-site wrappers, one reorder in _kickoff_turn, and two tests on the existing harness.
  Honors: Success criteria: an interrupted turn resumes at most once; human messages are not dropped. Constraint: watchdog stays non-blocking. Smallest change: no rework of merged feat_017_001; frugal testing on the existing SqliteSaver harness..

- `dec_012` · 2026-10-22 · Epic Manager · **Feature breakdown**
  Chose Amend dec_011's sequencing: feat_017_002 (already active, task_017_002_001 in progress) runs in parallel with feat_017_003 instead of waiting for it. feat_017_002 must use _graph_has_inflight_turn (dec_010) as the interrupted-turn test, not snapshot.next alone, and its restart test's interrupted checkpoint must hold a role message..
  Rationale: feat_017_002 started before feat_017_003 was minted. Its boot resume uses the resume_inflight job, which ingests only after resuming and never calls _stage_human_message, so it does not depend on gate item (c). Pausing it would be rework for no safety gain. Both features touch different branches of _kickoff_turn, so the second to merge rebases. Its spec still says 're-checks snapshot.next', which dec_010 showed would treat freshly seeded graphs as interrupted.
  Honors: Success criteria: an interrupted turn resumes at most once; graph settles idle after restart. Smallest change: no pause or rework of active feat_017_002..
## Amendment log

_(none)_
