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
- **Orphan sweep.** After any worker exit the launcher `killpg`s the worker's process group, which includes agent CLI subprocesses.
- **Drain then resume.** The worker drains: it answers writes with `503 updating`, finishes accepted HTTP handlers, and gives model turns a bounded window. Anything still unfinished goes to the existing checkpoint resume in the next worker.
- **Fail safe.** The old worker preflights the new source in a throwaway subprocess before draining. A failed preflight keeps the old worker serving. If a new worker never becomes ready, the launcher backs off and ends in a degraded responder (503 plus diagnostics on the same socket) that recovers automatically on the next source change.
- **Hosting contract.** External hosts (shell, tmux, systemd, containers) run `cascade up` once and only need to restart it if the *launcher* exits non-zero. That only happens for configuration or validation errors at startup. The design uses POSIX fd inheritance, process groups and flock, the same platform assumptions as today's lock. No daemon manager is required.

## Cross-module constraints

- Preserve the existing single-supervisor invariant and product-trunk workspace validation.
- Do not mix old and new Python modules within one long-lived process.
- Treat graph checkpoints, queues, comments, and worktree state as durable handoff boundaries.
- Avoid platform-specific daemon assumptions where possible; define a clear launcher/process contract for environments that host Cascade.
- Bound listener downtime and prevent restart storms through readiness checks, retry limits, and backoff.
- Keep operator-initiated shutdown distinct from source-triggered update restart.

## Core dependencies

- `cascade/workspace/up.py` (entry, source fingerprint), `cascade/workspace/lock.py` (`SupervisorLock`), `cascade/cli.py` (`up` command).
- `cascade/war_room/server.py` (`WarRoomHTTPServer`, `serve`): must accept a pre-bound socket and support a draining mode.
- `cascade/watchdog/loop.py` (`run_watchdog`, `stop_when`): must stop dispatch on drain.
- `cascade/workspace/kickoff.py` (`resume_inflight_graphs`, checkpoint inflight detection): the recovery path.
- `cascade/agent/cli_common.py`: agent subprocess lifetime and cancellation.
- Python stdlib only (`socket`, `subprocess`, `os`, `signal`, `fcntl`); no new third-party dependencies.

## Feature breakdown

1. **feat_018_001: Self-relaunching supervisor.** Launcher owns the lock and listener; the worker restarts on source change (exit 75); process-group sweep; readiness pipe; operator stop vs update. *Start first; this alone removes the outage.*
2. **feat_018_002: Graceful worker drain.** `503 updating` for writes, join accepted handlers, bounded turn drain, then exactly-once checkpoint resume. Depends on 001.
3. **feat_018_003: Update failure containment.** Preflight before drain, bounded backoff, degraded responder, `supervisor_status.json`, `/api/health`, War Room banner. Depends on 001; can run in parallel with 002.

Each feature owns its integration tests against a real `cascade up` subprocess and a fake provider. The epic's test criterion is covered across the three features: source-change detection and port continuity (001), active turns and queued events (002), failed startup and automatic recovery (003). No separate test-only feature.

### Explicitly cut

- Zero-downtime blue/green overlap of two workers. It conflicts with the single-supervisor invariant, and the socket backlog already prevents refused connections.
- In-process hot reload (`importlib.reload`). It violates the no-mixed-modules constraint.
- Shipping systemd/launchd units or Windows support.

## Open questions

- **Exactly-once resume (resolve before feat_018_002 builds cancellation):** if a model turn is cancelled after some tool effects (write_doc, record_decision, mint_feature, reply_comment) have landed but before the checkpoint advances, does resume replay them? The Epic Architect should confirm the checkpoint and tool-effect ordering in `cascade/*/checkpoint.py`, and decide between idempotency keys on effects and checkpointing per tool call. Until then, drain-first (wait out the window) is the default, and cancellation is the fallback.
- **Handler-thread draining (feat_018_002):** `daemon_threads=True` lets `server.shutdown()` abandon in-flight handlers. Confirm that switching to tracked, joined handler threads (bounded by `MAX_CONCURRENT_REQUESTS`) has no long-poll endpoints that would block the drain. Chat polling may need a short server-side timeout during drain.
- **Drain window default:** 120s is proposed. Revisit against `DEFAULT_CLI_TIMEOUT_SEC` and typical turn length. This is config, not architecture.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-10-23 · epic_manager · Architecture: long-lived launcher holds the lock and listening socket; a replaceable worker process per code version; sequential restart, no overlap.
- 2026-10-23 · epic_manager · Recovery reuses the existing checkpoint resume path (`resume_legally_active_graphs`) rather than a new state-transfer protocol.
- 2026-10-23 · epic_manager · Scope cuts: no blue/green overlap, no in-process hot reload, no platform daemon units.
- 2026-10-23 · epic_manager · Three-feature breakdown; 001 first, 002 and 003 in parallel after it; integration tests owned per feature.

## Amendment log

_(none)_
