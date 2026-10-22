---
id: task_017_002_001
title: Serialize boot resume through per-graph delivery path with bounded catch-up and delivery logging
tier: task
status: completed
parent: feat_017_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d5723a8194999f1a471b6c6f2ea623aa07572d52
created: '2026-10-22'
updated: '2026-10-22'
---
# Serialize boot resume through per-graph delivery path with bounded catch-up and delivery logging

## Parent Feature

[feat_017_002](../../features/2_active/feat_017_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
After a supervisor restart, every graph converges to idle. Interrupted turns resume at most once.

## Scope
- Route boot-time `resume_inflight_graphs` through the same serialized per-graph delivery path (per-graph lock) that feat_017_001 introduced for watchdog queue delivery. Do not add a second code path.
- Under the lock, re-read the checkpoint and re-check `snapshot.next` before resuming. If it is already cleared or advanced, skip it, so the resume runs at most once even if the watchdog races it.
- Graphs whose cursor fell behind before the fix catch up in a single bounded delivery (deliver the pending batch once, advance the cursor to EOF), then settle idle. No data migration.
- Emit one structured log line per delivery with `work_id`, `cursor_before`, `cursor_after`, `queue_size`, `turn_started`.

## Acceptance (system-level test)
- Simulated restart with an interrupted checkpoint (`next` set) and pending queue lines: model invocations stay bounded (assert an exact small count), the cursor ends at queue EOF, and the final checkpoint is idle (no `next`).
- Use a stub model provider. Avoid mock-heavy unit tests of the internals.

## Out of scope
Stall/duplicate-kickoff warnings (next task), dashboards, metrics, and watchdog performance.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
