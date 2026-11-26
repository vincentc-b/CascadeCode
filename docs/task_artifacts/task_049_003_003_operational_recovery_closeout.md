# Recovery progress and transcript operational evidence

## Pinned boundary

This proof runs on the Feature 4 handoff
`a3d4a42b3df92a553206c300c42142600183eaef`, which is an ancestor of this
checkout. It consumes
`tests/war_room/fixtures/recovery_progress_v1_epic_044.json`, the production
notification/publisher/action/transcript paths, and the versioned loopback HTTP
routes. The shared fixture supplies the incident action and generation contract;
the operational journey supplies the fixed source times and real durable IDs.

The source trace is:

1. `create_or_load_action` commits the 03:58:01 queued receipt and invokes the
   installed after-commit publisher.
2. `acknowledge_team_recovery` commits the 03:58:10 owner acknowledgement. The
   progress publisher now recognizes the production `owner_acknowledged` receipt
   and its nested routing timestamp as acknowledged evidence.
3. `resume_action` commits the 04:02:25 `execution_started` receipt, registers
   its exact executor identity, and then invokes the notification fast path. The
   progress page is therefore `executing` while the executor and final role reply
   are held.
4. `drain_recovery_progress` imports the separately committed claim receipt as
   `reconciled`; a second bounded drain imports zero receipts. Direct start and
   replay are distinct, receipt-key deduplicated paths.
5. A competing verified incident is published without replacing the live action.
   The transcript start anchor is visible over HTTP and Chromium before the held
   authored reply. Releasing the executor appends that reply and then its outcome;
   six material receipts produce six unique recovery milestones.

The journey preserves receipt, action, generation, attempt, claim, entry,
message and incarnation identity. Existing focused tests additionally exercise
pending source acknowledgement, incomplete legacy import, two real writer
processes, ordinary append high-water, room-move incarnation restart,
cross-graph/stale cursors, and positive UTF-8 detail continuation.

## Operational matrix

| Obligation | Evidence |
|---|---|
| Queued, acknowledged, executing, and held reply | `test_epic_044_held_reply_fast_path_replay_http_and_chromium` follows real action writes through notification, publication, loopback HTTP, service restart, and Chromium. |
| Investigating versus executing; missing token; dead, expired, inaccessible, and changed worker identity | `tests/recovery_progress/test_publisher.py` and `tests/workspace/test_live_observations.py`; only an exact invocation token supports investigating and only an exact executor token supports executing. |
| Wait, retry, exhaustion, generation mismatch, verification pending, authoritative verification | `test_public_states_require_their_matching_evidence` in `tests/recovery_progress/test_publisher.py`. |
| Direct notification versus restart replay | The operational journey asserts the direct start has `direct` provenance before bounded replay adds the missed claim with `reconciled` provenance; `tests/recovery_progress/test_transcript_milestones.py` covers missed notification and pending mapping repair. |
| Pending delivery/import and two writers | `test_pending_full_tail_is_unavailable_until_writer_replay`, resumable legacy-import tests, and `test_two_real_processes_deduplicate_one_source`. |
| Append, restart, detail, and graph fences | `tests/war_room/test_transcript_pages_api.py` covers ordinary after-cursor append, room-move incarnation restart, wrong-graph rejection, stale detail restart, and multibyte reconstruction with a positively advancing byte offset. |
| Read-only GET | During the journey, progress and transcript GETs remain green while writer-index, raw JSONL, provider probe, paid-turn admission, subprocess/Git, and checkpoint seams raise if called. Projection files are not repaired by GET. |

## Measured bounded reads

The scoped Chromium run on 2026-11-26 recorded the following representative
local measurements. They are runner observations, not universal latency claims.

| Read | Projection source bytes | HTTP response bytes | Rows |
|---|---:|---:|---:|
| Recovery progress | 4,077 | 4,514 | 3 |
| Transcript latest | 5,885 | 5,760 | 6 |

Both source measurements are below the 1 MiB aggregate ceiling, both responses
are below 256 KiB, and the request uses the 100-row maximum. Warm Chromium fetches
measured 37.0 ms for `/api/board` and 7.8 ms for the 100-row room page on this
run. The service was then restarted; the same transcript incarnation and start
anchor remained available.

The scoped browser proof passed independently. It does not resolve or reinterpret
Feature 4's broader documentation-refresh assertion, which remains unverified as
recorded by the pinned Feature plan.

## Validation

- `python -m pytest -q -s tests/war_room/test_transcript_pages_api.py::test_epic_044_held_reply_fast_path_replay_http_and_chromium` — 1 passed in 8.55 s with real Chromium.
- `python -m pytest -q tests/recovery_progress/test_publisher.py tests/recovery_progress/test_transcript_milestones.py tests/task/test_transition_receipts.py tests/war_room/test_transcript_pages_api.py tests/war_room/test_durable_chat_store.py -k 'not room_move_restarts_at_each_durable_boundary'` — 63 passed, 4 deselected in 78.23 s.
- `python -m pytest -q tests/workspace/test_live_observations.py tests/workspace/test_c4_source.py tests/war_room/test_recovery_progress_api.py` — 26 passed in 5.08 s.
- Final supervised validation is recorded by the Task delivery gate after the
  deliverable commit.

## Design and diagram impact review

Reviewed the affected recovery/transcript sections of `DESIGN.md`,
`cascade/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md`,
`cascade/workspace/DESIGN.md`, `cascade/war_room/DESIGN.md`, and the matching
symbols and relationships in pinned `model.dsl`, `views.dsl`, and
`workspace.contract.json` against the source diff.

| View | Reconciliation |
|---|---|
| `cascade-context`, `cascade-containers` | No actor, external dependency, deployment, persistence, or immutable GET boundary changed. |
| `cascade-war-room-components`, `cascade-dashboard-code` | No source symbol or relationship changed; the existing progress/transcript HTTP and browser nodes carry the new journey. |
| `cascade-supervisor-components`, `cascade-watchdog-code` | Existing publisher, bounded drain, milestone mapping, and immutable-page nodes match the exercised direct and replay flows. |
| `cascade-task-code` | `resume_action`, `_record_execution_start`, `_executor_live_identity`, and `_notify_transition` remain the owning nodes. The supplementary Task sequence was corrected so the exact token precedes the start notification and remains through execution. No node, declaration kind, ownership, or static relationship changed. |
| Workspace/Teams code views | Invocation-token behavior was verified but no Workspace or Teams source changed. A queued worker without the exact token remains non-executing. |

The only architecture deviation found was behavioral ordering inside the existing
Task nodes, so `cascade/task/DESIGN.md` was updated. Task 4 still owns final pinned
rendering, context-to-Code navigation, deep-link/Level-up/source-opening checks,
and integrated reconciliation of Feature 5's separately owned contention repair.
