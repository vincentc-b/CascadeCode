# Recovery routing design and C4 handoff

The integrated functional baseline is `469f0fa5f0bd99cf38351e26d6d7feb952bb26d3`
for fenced transcript mapping and
`ecd390f4d1819d72bc65e2ea4960000a48e50a67` for detail cursor refusal. The
parent handoff message records this artifact's exact deliverable SHA after commit.

## Design review and source traces

Reviewed `cascade/recovery_progress/DESIGN.md`, `cascade/watchdog/DESIGN.md`,
`cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`,
`cascade/DESIGN.md`, and root `DESIGN.md` against the final source. The new
recovery-progress child owns `REQ-RECOVERY-PROGRESS-001` through `004` and
`DEC-RECOVERY-PROGRESS-001` through `002`; Watchdog and package designs link to
that owner. War Room retains transcript requirements and decisions. Workspace
needed no change because room creation, movement, terminal retirement and
`resume_transcript_room_move` are unchanged.

Normal trace: `publish_committed_transition` appends or deduplicates the receipt,
begins the publisher transaction, and enters `_record_transcript_milestone`.
That helper calls `fenced_transcript_source_acknowledgement`, which acquires
`graph_transcript_fence`; the publisher inserts or refreshes current routing,
updates the entry, commits SQLite and only then exits the fence. Delayed/failure
trace: rewrite or move wins the graph fence before the delayed writer, so the
writer rereads current routing; pending intent, incomplete indexing or missing
room raises pending, leaves the mapping absent or unchanged and keeps bounded
drain/restart replay eligible. Immutable receipt, entry, graph and message
conflicts are refused.

## Diagram impact

| View | Symbols and owner | Treatment and verification |
|---|---|---|
| `cascade-landscape`, `cascade-context` | Recovery publisher and transcript store; root design | No actor, external system or responsibility boundary changed. Retained after source/diff review and successful 24-view render. |
| `cascade-containers` | Publisher SQLite and transcript JSONL/index; `cascade/DESIGN.md` | Both stores remain inside the existing Service/War Room storage boundaries; no deployment or isolation change. Browser traversed the retained container view. |
| `cascade-supervisor-components` | `publish_committed_transition`, `drain_recovery_progress`, `_record_transcript_milestone`; recovery-progress owner | Existing Watchdog component remains the producer boundary. No component edge change; browser traversed it to native Code. |
| `cascade-war-room-components` | `fenced_transcript_source_acknowledgement`, `graph_transcript_fence`, `read_transcript_detail`; War Room | Existing Dashboard/transcript boundary remains valid. Browser traversed it to native Code. |
| `cascade-watchdog-code` | `_record_transcript_milestone`, public writer, fast path and drain; recovery-progress owner | Integrated model contains Function nodes and fast-path, drain and public-writer edges to the private helper. Browser restored its deep link and opened pinned publisher source. |
| `cascade-dashboard-code` | `fenced_transcript_source_acknowledgement`, `graph_transcript_fence`, `_connect_index`, `read_transcript_detail`; War Room | Integrated model contains the separate source-lookup Function node and edges to graph fence/index plus the detail Function node. Browser opened both pinned sources. |
| `cascade-workspace-code` | `move_transcript_room`, `resume_transcript_room_move`, retirement caller; Workspace/War Room | Move behavior and symbols did not change. The retirement-to-resume relationship, semantic IDs and declaration kinds remain in the source contract. |

`model.dsl`, `views.dsl` and `workspace.contract.json` validate together with 235
elements, 283 relationships and 24 views. The mapping/source-fence nodes and
relationships are present in all three artifacts. No renamed or deleted affected
symbol was found. Browser integration exposed a 413 because each view page
repeated all 518 semantic element/relationship targets. Snapshot pages now carry
their represented targets and the client losslessly merges them by semantic ID,
preserving the route and 256 KiB cap.

## Verification and Feature handoff

- Focused publisher, milestone, store, transcript API, source-contract,
  architecture pagination and tab checks: 77 passed in 65.58 s.
- Source-contract validation: 235 elements, 283 relationships and 24 views.
- Real pinned renderer/cache test: passed; the second submission was a cache hit
  and reused the first artifact directory and binding manifest.
- Actual-model Chromium probe: ready in 51.833 s; traversed context → containers
  → Watchdog/Dashboard components → native Code, restored the Watchdog Code deep
  link, used Level up, and opened pinned source for publisher mapping, source-key
  lookup and detail reading. Three warm board reads took 0.032 s and retained one
  render operation (`1 → 1`), so navigation did not start per-view render work.
- Ruff and `git diff --check`: passed.

The route/header/error/detail fixture is
`tests/war_room/test_transcript_pages_api.py`, especially
`test_typed_invalid_restart_pending_and_get_is_projection_only` and
`test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor`.
The latter reconstructs the oversized multibyte body, asserts positive byte
continuation, and mutates the opaque offset into an emoji to require typed HTTP
400 `invalid_request`. Milestone fixtures are
`tests/recovery_progress/test_transcript_milestones.py`; store movement/pending
fixtures are `tests/war_room/test_durable_chat_store.py`.

One broader browser journey reached and passed its render/navigation/source/cache
assertions but later failed an unrelated refreshed-documentation assertion; the
actual-model focused browser probe is the scoped navigation gate. No Epic
acceptance is claimed and no other team's completed board record was changed.
