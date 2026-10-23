---
id: epic_018
title: Graceful supervisor updates without War Room outage
tier: epic
status: active
parent: null
children:
- feat_018_001
- feat_018_002
- feat_018_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-23'
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Graceful supervisor updates without War Room outage

## Intent

Cascade currently detects changes to its loaded Python source and exits with a restart-required error. When the hosting process does not relaunch it, the War Room listener disappears and SSH-forwarded clients receive connection-refused errors until an operator manually restarts the supervisor. Replace this failure mode with a controlled update lifecycle that safely hands off or restarts the supervisor, preserves durable workflow state, and restores service automatically.

### Success criteria

- A detected Cascade source change initiates a controlled restart or process handoff instead of terminating into an unrecovered failure state.
- The War Room automatically resumes listening on the configured host and port without manual intervention.
- In-flight planning and task work is drained when possible or recovered exactly once from durable checkpoints after restart.
- The supervisor lock and listener socket transfer cleanly, with no overlapping active supervisors, orphaned agent subprocesses, or stale-lock blockage.
- New HTTP work is stopped or rejected with an explicit transient updating response during shutdown; accepted writes are not lost.
- Update progress and failures are visible through logs and UI health/status, including actionable diagnostics when automatic recovery cannot complete.
- A failed replacement process leaves the last viable service running when feasible, or retries with bounded backoff rather than silently remaining offline.
- Integration tests exercise source-change detection, active model turns, queued events, port rebinding, failed replacement startup, and successful automatic recovery.

## Macro-architecture

### Current state (grounded in code)

- `cascade/workspace/up.py::up()` takes `SupervisorLock` (flock on `.cascade/supervisor.lock`), builds `WarRoomHTTPServer` (stdlib `ThreadingHTTPServer`, `daemon_threads=True`), runs `resume_legally_active_graphs`, then blocks in `run_watchdog`. Every 1s it hashes `cascade/**/*.py`; on change it shuts the server, releases the lock and raises `WorkspaceError`. Nothing relaunches it.
- Restart recovery already exists: `resume_inflight_graphs` re-queues interrupted turns and lagging queue cursors from graph checkpoints. This epic reuses that path instead of building a new handoff protocol.
- Agent turns run as provider CLI subprocesses (`cascade/agent/cli_common.py`, `asyncio.create_subprocess_exec`) in the supervisor's process group, so a killed supervisor can orphan them.

### Target: launcher + replaceable worker (sequential restart, inherited socket)

```
cascade up (launcher, long-lived, stdlib-only loop)
  ├─ prepare_up() validation, SupervisorLock held for launcher lifetime
  ├─ binds 127.0.0.1:port once; keeps the listening fd open across workers
  ├─ writes .cascade/supervisor_status.json
  └─ spawns worker:  python -m cascade.workspace.worker  (new process group,
       inherited listen fd + readiness pipe + lock token env)
         ├─ WarRoomHTTPServer on the inherited fd
         ├─ resume_legally_active_graphs + run_watchdog
         └─ on source change: preflight -> drain -> exit 75
```

- **Lock and socket never move.** The launcher holds both for its whole life, so there is never a window with two supervisors or a released lock. The worker only runs with the launcher handshake.
- **No connection-refused gap.** Because the listening socket stays bound in the launcher, connections during a restart wait in the kernel backlog and are served by the next worker. The "port rebinding" criterion is met by never unbinding.
- **Fresh process per code version.** Each worker imports the current source once; the launcher does not import changing Cascade modules after start. Old and new modules are never mixed in one process.
- **Exit-code contract (worker to launcher):** `0` operator stop, the launcher exits. `75` update, relaunch now. Anything else is a crash: relaunch with bounded backoff. Operator SIGINT/SIGTERM goes to the launcher, which forwards a stop. This keeps operator shutdown distinct from update restarts.
- **Orphan and stale-lock sweep.** After any worker exit the launcher `killpg`s the worker's process group, which includes agent CLI subprocesses and their stdio MCP tool servers. Once the group is gone, any `.git/index.lock` left in a Cascade-managed worktree (`.cascade/worktrees/*`) is stale by construction, because the launcher holds the supervisor lock, and is removed with a log line. A leftover `index.lock` in the product trunk is only reported in diagnostics, because a human may be running git there.
- **Drain then resume.** The worker drains: it answers writes with `503 updating`, finishes accepted HTTP handlers, and gives model turns a bounded window. Anything still unfinished goes to the existing checkpoint resume in the next worker.
- **Fail safe.** The old worker preflights the new source in a throwaway subprocess before draining. A failed preflight keeps the old worker serving. If a new worker never becomes ready, the launcher backs off and ends in a degraded responder (503 plus diagnostics on the same socket) that recovers automatically on the next source change.
- **Hosting contract.** External hosts (shell, tmux, systemd, containers) run `cascade up` once and only need to restart it if the *launcher* exits non-zero. That only happens for configuration or validation errors at startup. The design uses POSIX fd inheritance, process groups and flock, the same platform assumptions as today's lock. No daemon manager is required.

### Turn recovery semantics (resolved by Epic Architect)

Findings from code:

- Graph checkpoints (`cascade/{epic,feature,task}/checkpoint.py`, LangGraph `SqliteSaver`) persist only at **node boundaries**. A role turn (for example the epic `manager` or `architect` node) is one node that runs one whole agent CLI session.
- Board tools apply their effects **synchronously, during the turn**. Tool calls go from the agent CLI to the `cascade.agent.mcp_stdio` subprocess (or to in-process custom tools for Cursor), then through `dispatch_planning_tool` to `invoke_tool`, which writes and commits on disk at once. They never pass through War Room HTTP, so the drain's `503 updating` does not affect in-flight turns.
- The queue cursor (`last_queue_offset`) is committed **before** the turn starts, and `snapshot.next` marks the role node as in flight. On restart, `_resume_inflight_turn_if_needed` re-invokes that node **from the start**, at most once per resume.
- The per-turn effect journal (`.cascade_effects.jsonl`) lives in the scratch sandbox and is deleted after every turn, so resume cannot see it.
- `board/store.py::write_doc` uses a non-atomic `write_text` and then a git commit. A kill during a tool call can leave a truncated doc or a stale `.git/index.lock`.

Consequences and contract:

- **Turn delivery is at-least-once, and the resumed turn re-runs in full.** Queued events are never lost. Effects that landed before the kill **are** replayed unless the tool is replay-safe.
- `write_doc` is a full-body compare-and-swap on `sha`, and the re-run re-reads the doc first, so it is replay-safe as is. `resolve_amendment` is a state transition and is replay-safe if it treats an already-resolved amendment as a no-op.
- `record_decision`, `mint_feature` and `reply_comment` append or create, so they are **not** replay-safe. They become idempotent on a natural key: an identical decision (same section and choice) already in the log, a child feature with the same title under the same parent, or an identical reply body by the same author on the same comment. In each case the tool returns the existing id and does nothing. The `append_event` inside `mint_feature` fires only on an actual creation.
- Doc writes become atomic (write a temp file in the same directory, then `os.replace`). Together with the stale `index.lock` sweep, this means a kill can never corrupt a doc or block the next commit.
- "Recovered exactly once" therefore means the following: each interrupted turn is resumed once, and none of its landed effects is applied twice. A resumed model may still choose *different* wording for something it already did. That is the same as an operator re-running a turn. It is acceptable and is not deduplicated.
- Per-tool-call checkpointing was rejected. A provider CLI session cannot be resumed partway through, so the node would still re-run from the start. It would add graph machinery without removing the replay.
- **Cancellation is a normal path, not a rare fallback.** `DEFAULT_CLI_TIMEOUT_SEC` is 3600s, so turns can far outlast any sensible drain window. When the window expires, the worker sends SIGTERM to each agent's process group, waits a short grace period (5s), and then exits 75. The launcher's `killpg` covers anything left.

### HTTP handler drain (resolved by Epic Architect)

- There are no long-poll or streaming endpoints. The War Room has no blocking waits outside `WarRoomRequestHandler.handle`, and chat is fetched by a plain GET. Every connection already has a hard per-route deadline: `REQUEST_DEADLINE_S` (10s), or `APPROVAL_DEADLINE_S` / `EPIC_CLOSE_DEADLINE_S` (60s) for the approval and epic-close POSTs.
- Drain switches the server to tracked, non-daemon handler threads (at most `MAX_CONCURRENT_REQUESTS`) and joins them, bounded by the longest route deadline plus a small margin (about 65s). Handlers that are still running after that are logged and abandoned. Their side effects go through the same replay-safe tools and atomic writes as above.
- While draining, every response sets `Connection: close`, so idle HTTP/1.1 keep-alive connections do not hold handler threads. Reads (GET) keep being served until the join finishes, and writes get `503 updating` with `Retry-After`.
- The HTTP join and the turn drain run concurrently, so the worst-case drain is about max(turn window, 65s), plus the 5s grace.

## Cross-module constraints

- Preserve the existing single-supervisor invariant and product-trunk workspace validation.
- Do not mix old and new Python modules within one long-lived process.
- Treat graph checkpoints, queues, comments, and worktree state as durable handoff boundaries.
- Every board tool effect must be replay-safe, because a resumed turn re-runs its whole role node. New tools that append or create must declare their natural idempotency key.
- A board write interrupted by a kill must not corrupt a doc or leave a lock that blocks the next commit.
- Avoid platform-specific daemon assumptions where possible; define a clear launcher/process contract for environments that host Cascade.
- Bound listener downtime and prevent restart storms through readiness checks, retry limits, and backoff.
- Keep operator-initiated shutdown distinct from source-triggered update restart.

## Core dependencies

- `cascade/workspace/up.py` (entry, source fingerprint), `cascade/workspace/lock.py` (`SupervisorLock`), `cascade/cli.py` (`up` command).
- `cascade/war_room/server.py` (`WarRoomHTTPServer`, `serve`): must accept a pre-bound socket and support a draining mode.
- `cascade/watchdog/loop.py` (`run_watchdog`, `stop_when`): must stop dispatch on drain.
- `cascade/workspace/kickoff.py` (`resume_inflight_graphs`, `_resume_inflight_turn_if_needed`): the recovery path.
- `cascade/agent/cli_common.py`: agent subprocess lifetime and cancellation.
- `cascade/board/store.py` (`write_doc`), `cascade/epic/decisions.py`, `cascade/feature/decisions.py`, `cascade/epic/mint.py`, `cascade/comments/store.py`: replay-safe and atomic effects.
- Python stdlib only (`socket`, `subprocess`, `os`, `signal`, `fcntl`); no new third-party dependencies.

## Feature breakdown

1. **feat_018_001: Self-relaunching supervisor.** Launcher owns the lock and listener; the worker restarts on source change (exit 75); process-group sweep plus stale `index.lock` sweep in Cascade-managed worktrees; readiness pipe; operator stop vs update. *Start first; this alone removes the outage.*
2. **feat_018_002: Graceful worker drain.** `503 updating` for writes, `Connection: close` while draining, tracked handler threads joined within the longest route deadline, bounded turn drain with SIGTERM-then-exit cancellation, replay-safe `record_decision` / `mint_feature` / `reply_comment` / `resolve_amendment`, atomic doc writes, then checkpoint resume. Depends on 001.
3. **feat_018_003: Update failure containment.** Preflight before drain, bounded backoff, degraded responder, `supervisor_status.json`, `/api/health`, War Room banner. Depends on 001; can run in parallel with 002.

Each feature owns its integration tests against a real `cascade up` subprocess and a fake provider. The epic's test criterion is covered across the three features: source-change detection and port continuity (001), active turns and queued events (002), failed startup and automatic recovery (003). No separate test-only feature. For 002, one integration test covers the replay contract: a fake-provider turn calls `record_decision` and `mint_feature`, and is then cancelled by an update before its node completes. After resume, the board must show exactly one decision and one feature. Idempotency gets no per-tool unit-test matrix.

### Explicitly cut

- Zero-downtime blue/green overlap of two workers. It conflicts with the single-supervisor invariant, and the socket backlog already prevents refused connections.
- In-process hot reload (`importlib.reload`). It violates the no-mixed-modules constraint.
- Shipping systemd/launchd units or Windows support.
- Per-tool-call graph checkpointing and a durable cross-worker effect journal. Natural-key idempotency covers replay with less machinery.

## Open questions

- **Drain window default:** 120s, as config. Turns can run up to 3600s, so expect long turns to be cancelled and resumed on every update. Raise the default only if resume cost shows up in practice.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-23 · Epic Manager · **Macro-architecture**
  Chose A long-lived launcher holds the supervisor lock and the listening socket for its whole life and spawns one replaceable worker process per code version, restarting sequentially with no overlap. The worker exits 75 on a source update, 0 on operator stop, and any other code counts as a crash..
  Rationale: Never releasing the lock or unbinding the port removes the connection-refused window and stale-lock risk. A fresh process per version avoids mixing modules. This is far less machinery than blue/green handoff or fd passing between peers.
  Honors: Single-supervisor invariant; no mixed old/new modules; operator shutdown distinct from update restart; launcher/process contract without platform daemons..

- `dec_002` · 2026-10-23 · Epic Manager · **Feature breakdown**
  Chose Cut blue/green overlap of two workers, in-process importlib hot reload, shipped systemd/launchd units, and Windows support.
  Rationale: Keeping the socket bound in the launcher already removes refused connections, so overlap buys only seconds and costs the single-supervisor guarantee. Hot reload mixes modules. Daemon units and Windows serve no stated user problem and fcntl locking is already POSIX-only
  Honors: Single-supervisor invariant; no mixed modules; avoid platform-specific daemon assumptions.

- `dec_003` · 2026-10-23 · Epic Manager · **Feature breakdown**
  Chose Three features: feat_018_001 (launcher/worker relaunch) first; feat_018_002 (graceful drain) and feat_018_003 (preflight, backoff, degraded responder, health) in parallel after it. Each owns its integration tests against a real cascade up subprocess; no separate test-only feature.
  Rationale: 001 alone removes the outage and is the smallest shippable slice. 002 and 003 touch different seams (worker shutdown vs launcher retry/status) so they can proceed concurrently. System-level tests per feature give high signal without a redundant test feature
  Honors: Bounded downtime and restart-storm prevention; integration-test success criterion; frugal testing.

- `dec_004` · 2026-10-23 · Epic Manager · **Macro-architecture**
  Chose Recover interrupted work through the existing checkpoint resume path (resume_legally_active_graphs / resume_inflight_graphs) after a bounded drain, instead of building a new live state-transfer protocol between workers.
  Rationale: The durable checkpoints, queues and worktrees already survive a process restart, and resume is already exercised on every startup. Adding a second handoff mechanism would duplicate it and add risk. The remaining exactly-once gap for cancelled turns is tracked as an open question for the Epic Architect
  Honors: Checkpoints, queues, comments and worktree state as durable handoff boundaries; drain when possible, recover exactly once otherwise.

- `dec_005` · 2026-10-23 · Epic Architect · **Macro-architecture**
  Chose Make turn recovery exactly-once by making every board tool replay-safe on a natural key (record_decision by section+choice, mint_feature by parent+title, reply_comment by comment+author+body, resolve_amendment as a no-op when already resolved), keeping write_doc's sha compare-and-swap, and treating turn delivery as at-least-once; per-tool-call checkpointing rejected.
  Rationale: Code shows checkpoints persist only at role-node boundaries, tools commit to disk synchronously during the turn, and resume re-runs the whole node, so landed effects are replayed today. A provider CLI session cannot resume partway through, so per-tool checkpoints would not stop the node re-running; idempotent tools fix replay for update cancels and ordinary crashes alike, with one integration test
  Honors: In-flight work recovered exactly once from durable checkpoints; checkpoints, queues and comments as durable handoff boundaries; frugal testing.

- `dec_006` · 2026-10-23 · Epic Architect · **Macro-architecture**
  Chose Drain HTTP by switching to tracked non-daemon handler threads joined within the longest route deadline plus margin (about 65s), sending Connection: close on every response while draining, serving GETs and answering writes with 503 updating until the join finishes.
  Rationale: The War Room has no long-poll or streaming endpoints and every connection already has a hard per-route deadline (10s, or 60s for approvals and epic close), so the join is bounded without new timeouts. Connection: close stops idle keep-alive sockets from holding threads
  Honors: New HTTP work rejected with an explicit updating response; accepted writes not lost; bounded listener downtime.

- `dec_007` · 2026-10-23 · Epic Architect · **Macro-architecture**
  Chose Make kills safe: doc writes become atomic (temp file then os.replace); after killpg the launcher removes stale .git/index.lock files in Cascade-managed worktrees and only reports one in the product trunk; drain-window expiry sends SIGTERM to agent process groups, waits 5s, then exits 75.
  Rationale: board/store.py writes with non-atomic write_text and then commits, so a kill mid-tool can truncate a doc or leave index.lock blocking every later commit. With turns allowed up to 3600s, cancellation happens on most updates, not rarely. Holding the supervisor lock with the old group dead makes Cascade-worktree locks stale by construction; the trunk may have a human running git
  Honors: No orphaned subprocesses or stale-lock blockage; accepted writes not lost; product-trunk workspace validation.
## Amendment log

_(none)_
