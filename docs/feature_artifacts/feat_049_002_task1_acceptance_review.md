# Task 1 integrated acceptance review

Integrated source revision: `bd152f61d39912f920830250c62efc57050d689c`.
The task is canonically completed, but Feature acceptance remains open.

## Required canonical Task-record correction

The completed Task record still has `TBD` acceptance, files, test plan and out-of-scope fields, plus a stale Parent Feature link. `revise_task` only admits backlog, ready-to-plan or blocked Tasks; an authorized board correction for this completed record is still needed. This artifact records the requested text and does not claim the Task record changed.

- Parent Feature: `../../features/2_active/feat_049_002_persist_recovery_milestones_and_bounded_transcript_history.md`.
- Acceptance: owning JSONL authority; tracking-root graph OS fence for append, remove, sync and room movement; writer-only SQLite unique message/source keys, sequence, offsets, indexed end, room/incarnation and one durable exact-line intent; intent commit, JSONL append/fsync, index commit/clear, fence release, then acknowledgement; matching empty/partial/full tail repair only; uncertain owner, unexpected bytes, torn legacy and conflicting destination remain pending without truncation; bounded 1 MiB/100-row resumable legacy import preserving IDs, append fields and null source occurrence; split-root routing and incarnation change; no source lifecycle lock nesting, scheduler, GET repair or new authority.
- Files: `cascade/war_room/chat_store.py`, `cascade/war_room/planning_transcript.py`, `cascade/workspace/integration_worktree.py`, `cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`, pinned `model.dsl`, `views.dsl`, `workspace.contract.json`, and `tests/war_room/test_durable_chat_store.py`.
- Test plan: `pytest -q tests/war_room/test_durable_chat_store.py tests/workspace/test_integration_worktrees.py`.
- Out of scope: milestone consumer and replay; authored-reply checkpoint identity; immutable pages and bounded v1/legacy HTTP reads; scheduler or GET-side repair.

## Crash boundaries to repair

1. `chat_store.py::_repair_pending`: a fully present intended line skips `_append_and_fsync` and proceeds to `_commit_intent`. Process death after write but before fsync can leave visible, volatile bytes; replay must sync the file and required directory before clearing the intent. The existing empty/partial/full-tail test checks bytes, not this ordering.
2. `chat_store.py::move_transcript_room`: it unlinks and syncs the source before `switch_owner` and `_reset_room_index`. Process death leaves the index and registry pointing to a missing source while the copied destination exists. Retry rejects that state as an uncertain source. Terminal retirement also lets `switch_owner` remove the worktree, so interruption after owner switch needs a durable resume path.

Repair owner: `task_049_002_005`. Tasks 2 and 3 retain their separate interfaces. Task 4's integrated acceptance must include the repaired crash paths before Feature sign-off.

## Design review and impact

Reviewed `cascade/war_room/DESIGN.md` and `cascade/workspace/DESIGN.md` against the integrated `chat_store.py`, `planning_transcript.py`, `integration_worktree.py`, `tests/war_room/test_durable_chat_store.py`, and pinned `model.dsl`, `views.dsl`, `workspace.contract.json`. The designs describe the intended fence, intent, copy and switch; they do not establish recovery after the two crash points above. Context and container boundaries remain the same. The War Room component and `cascade-dashboard-code` own replay and move implementation; Workspace and `cascade-workspace-code` own dispatch and terminal owner switching. Task 5 must reconcile these views and the normal/failure sequence with the corrected code, verify source symbols/kinds and navigation, and record actual tests and local render results. This review is source tracing; no fault-injection validation has run for the gaps yet.
