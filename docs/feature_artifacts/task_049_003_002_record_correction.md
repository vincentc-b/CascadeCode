# Task 2 canonical-record correction handoff

The completed Task 2 board record points to a nonexistent Parent Feature path and retains preimplementation notes. The exact corrected replacement body submitted to Cascade MCP `revise_task` is below. Cascade returned `task_049_003_002 cannot be revised while completed`. Its lifecycle metadata and frontmatter remain authoritative in the board; this artifact does not change the canonical Task record.

```markdown
# Render durable Historical transcript pages and recovery milestones

## Parent Feature

[feat_049_003](../../features/2_active/feat_049_003_show_coherent_recovery_progress_on_board_and_historical_transcript.md)

## Depends on

- task_049_003_001

## Acceptance criteria

- Bind page, detail, legacy-header and typed error behavior to `tests/war_room/test_transcript_pages_api.py::test_typed_invalid_restart_pending_and_get_is_projection_only` and `::test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor` on Feature 4 handoff `a3d4a42b3df92a553206c300c42142600183eaef`; incomplete detail chunks advance UTF-8 byte offsets positively and reconstruct exact text.
- Use `tests/recovery_progress/test_transcript_milestones.py` for committed mapping and `tests/war_room/test_durable_chat_store.py::test_fenced_source_lookup_leaves_pending_intent_for_writer_repair` for pending evidence. Keep progress revision distinct from transcript incarnation and reject stale graph/incarnation responses.
- Diagram impact: inspect `cascade-war-room-components`, `cascade-dashboard-code` and affected `cascade-war-room-http-code` source symbols, source contract and War Room design; give context/container no-change reasons grounded in the diff. Preserve producer ownership in `cascade/recovery_progress/DESIGN.md`.

- Use versioned latest, older and after transcript pages with stable graph/incarnation/message identity; preserve older high-water and scroll under appends.
- Render System · Recovery milestones separately from authored manager/architect and human messages; preserve older dated claims, nullable occurrence and provenance.
- Resolve only committed milestone_refs; show pending delivery, incomplete import and history_pending.
- Provide keyboard access, safe local links and bounded preview/detail continuation; refuse wrong graph, stale incarnation/detail and late responses without mixing history.
- Reconcile War Room design and affected Dashboard Code nodes with real declarations, source contract and normal/failure flow.

## Files likely touched

cascade/war_room/static/war_room.js; War Room template/style; cascade/war_room/DESIGN.md; architecture model/views/contract only if actual symbols change.

## Implementation notes

Merged implementation `6b1087165e3132be0e944d453749c0b381feeca7` and follow-up `1727c75779dcb5ef95e609f252568029904245f0` render versioned latest, older and after pages, committed recovery milestone anchors, typed pending/restart states and bounded UTF-8 detail continuation. The follow-up refreshes current progress during open-room transcript polling with one bounded request in flight while retaining scroll and paging high-water. War Room design and Dashboard Code symbols were reconciled. Task 3 owns the held-final-reply and cross-process operational proof; Task 4 owns final integrated architecture navigation.

## Skills

_(none)_

## Test plan

Supervised clean-tree Task validation reported 73 passed in 124.44 seconds. On the integrated feature branch, `node tests/war_room/war_room_refresh_races.mjs`, `python -m pytest -q tests/war_room/test_transcript_pages_api.py -k historical_ui_pages_milestones_and_bounded_detail` (1 case), `python -m pytest -q tests/workspace/test_c4_source.py` (14 cases), and `git diff --check 1c7fbea9..HEAD` passed. These checks cover local browser paging, anchors, detail and source symbols. They do not establish the held-final-reply notification journey, cross-process replay, Feature 5 contention bound, rendered C4 navigation or live deployment.

## Out of scope

No producer ledger or recovery authority changes.
```
