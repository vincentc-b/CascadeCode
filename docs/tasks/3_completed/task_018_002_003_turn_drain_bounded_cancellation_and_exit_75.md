---
id: task_018_002_003
title: Turn drain, bounded cancellation, and exit 75
tier: task
status: completed
parent: feat_018_002
children: []
depends_on:
- task_018_002_002
owners:
- swe
skills: []
parent_rev: e409e71d8ab73ebc5f93ae946f44301b84b8ed36
created: '2026-10-23'
updated: '2026-10-23'
---
# Turn drain, bounded cancellation, and exit 75

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

- task_018_002_002

## Acceptance criteria

Contracts: feature spec "Data structures" (live-turn registry, cancellation error, config, constants) and "API contracts" (Turn admission gate, Turn registry and cancellation, Worker shutdown); feature dec_008, dec_012.

- **Admission gate in `cascade/workspace/kickoff.py`:** `_submit_background` drops the job when `is_draining()` (from `cascade/workspace/drain.py`), and `_drain_background` checks `is_draining()` before running each dequeued job. Dropped jobs are logged at info, still `task_done()`, never executed, and advance no queue cursor and write no checkpoint. `run_watchdog` already stops via `stop_when()`; no other watchdog change. If a job kind turns out not to be re-derivable from a graph queue or in-flight checkpoint, raise an upward question instead of persisting new state.
- **Live-turn registry in `cascade/agent/turn_registry.py`** (new): `LiveTurn(turn_id, role, loop, task, pid=None, cancelled=False)`, `_live` guarded by a `threading.Lock`; `register_turn(role)` context manager entered inside the running task at `run_role` in `cascade/agent/adapter.py`, so every provider (claude, codex, cursor-sdk, fake) registers; `set_current_turn_pid(pid)` (no-op when unregistered) called by `run_subprocess_turn` right after `create_subprocess_exec` via a `ContextVar[LiveTurn | None]`; `live_turns()`, `wait_until_idle(timeout) -> bool`, `cancel_live_turns()`.
- **Cancellation:** for each live turn, set `cancelled = True`; if `pid` is set, `os.kill(pid, SIGTERM)` ignoring `ProcessLookupError`; then `loop.call_soon_threadsafe(task.cancel)`. **SIGTERM the agent pid, not a process group**: no `killpg`, no `start_new_session` (epic dec_010). The launcher's `killpg` of the worker group (feature 1) is the backstop; do not duplicate it.
- **`TurnCancelledForDrain(Exception)` in `cascade/agent/errors.py`:** `run_role` raises it for any turn whose `cancelled` flag is set, whether it ended by `CancelledError`, by a non-zero CLI exit after SIGTERM, or by an SDK error.
- **Propagation so cancelled work is neither finished nor failed:** `cascade/agent/graph_turn.py` and `cascade/task/swe_turn.py` do not catch it in provider/startup `except` clauses and do not turn it into `run_error_message` text; it leaves the role node before any node-boundary checkpoint is written. `kickoff._run_background_kickoff` catches it first, logs at info, and does not call `fail_task` or `append_transcript_message`.
- **Config:** `[worker] drain_seconds` in `cascade.toml`, read by `cascade/watchdog/config.py::worker_drain_seconds(root) -> float`. Missing key gives 120.0; a non-positive, bool or non-numeric value logs a warning and gives 120.0 (never raises). Read once in `run_worker` before serving and passed to `drain_and_shutdown`.
- **Turn side of `drain_and_shutdown` in `cascade/workspace/worker.py`:** in its own thread, concurrent with the HTTP join, run `wait_until_idle(drain_seconds)`; if turns remain, `cancel_live_turns()` then `wait_until_idle(CANCEL_GRACE_S)` (`CANCEL_GRACE_S = 5.0`). For `reason="crash"`, the window is 0: cancel immediately, then wait for the grace period. `server.shutdown()` runs only after both the HTTP join and the turn drain finish. The stderr summary line also counts joined and cancelled turns.
- **Exit:** 75 for update, 0 for operator stop; `os._exit(code)` after flushing stdio when any handler was abandoned.
- Cancelled turns are resumed once by the next worker through the existing `resume_legally_active_graphs` / `deliver_queue_kickoffs`. No new resume mechanism.

### Check what task 002 merged

Task 002's doc could not be revised while it was active. Before starting, confirm its merge matches the feature spec: flag in `drain.py` (not a raising accessor in `worker.py`), the listener keeps accepting until after the drain (no early `server.shutdown()`), the join waits on the drain-start snapshot, `drain_and_shutdown` exists in `worker.py`, and `main()` uses `os._exit` when handlers are abandoned. Finish any missing piece of `drain_and_shutdown` or the exit path in this task. If the HTTP behavior itself (503/`Connection: close`/snapshot join) is wrong, raise it upward instead of reworking `server.py` here.

## Files likely touched

- `cascade/agent/turn_registry.py` (new)
- `cascade/agent/errors.py`
- `cascade/agent/adapter.py` (`run_role`, `run_subprocess_turn`)
- `cascade/agent/graph_turn.py`
- `cascade/task/swe_turn.py`
- `cascade/workspace/kickoff.py`
- `cascade/watchdog/config.py`
- `cascade/workspace/worker.py`

## Implementation notes

The fake provider must go through `run_role` so it registers with `pid=None` and is cancelled by `task.cancel`; test (b) in task 004 depends on this. Cursor-sdk turns are cancelled the same way, since the bridge pid is SDK-private. Correctness depends on no node-boundary checkpoint being written when a role node raises (epic dec_005). If that premise turns out false, raise it upward rather than adding per-tool checkpoints.

## Skills

_(none)_

## Test plan

No new unit tests; integration tests (b) and (c) in task_018_002_004 cover this task. Keep existing `tests/` for `graph_turn`, `swe_turn`, `kickoff` and the watchdog config green, adjusting only where the new `except` ordering or `run_role` wrapper breaks them.

## Out of scope

HTTP drain behavior (task 002). Integration tests (task 004). Process groups, `killpg`, and any launcher change (epic dec_010/dec_011). Per-tool-call checkpointing.
