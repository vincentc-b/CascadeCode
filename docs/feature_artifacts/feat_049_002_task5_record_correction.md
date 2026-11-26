# Task 5 canonical record correction handoff

The completed Task record still has a stale Parent Feature link and duplicate
Acceptance criteria, Files likely touched, Test plan and Out of scope headings.
The first and last copies contain `TBD.`; the substantive text is nested under
Implementation notes. The Task owner reported `path not allowed` from the
SWE commit guard. The completed lifecycle does not admit `revise_task`; this
artifact does not replace an authorized board correction.

## Exact correction

- Parent Feature: `[feat_049_002](../../features/2_active/feat_049_002_persist_recovery_milestones_and_bounded_transcript_history.md)`.
- Acceptance criteria: use the five numbered criteria currently in the record's
  Implementation notes, including fully visible tail fsync before index commit,
  fsync failure retaining intent, crash-safe room movement, exact byte conflicts
  remaining pending, split-root and terminal retirement restart tests, and
  War Room/Workspace design plus native Code reconciliation. Add the delivered
  rewrite-intent recovery gate: original or replacement fingerprint only;
  preserve retained message IDs/source keys and target incarnation after a
  process death between JSONL replacement and SQLite index reset.
- Files likely touched: `cascade/war_room/chat_store.py`,
  `cascade/workspace/integration_worktree.py`,
  `cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`, pinned
  `model.dsl`, `tests/war_room/test_durable_chat_store.py`, and
  `tests/workspace/test_integration_worktrees.py`.
- Test plan: `pytest -q tests/war_room/test_durable_chat_store.py
  tests/workspace/test_integration_worktrees.py tests/workspace/test_c4_source.py`;
  validate the pinned source contract and real local renderer.
- Out of scope: receipt milestone consumer, authored reply identity, bounded
  transcript HTTP pages, scheduler, GET repair and unrelated lifecycle policy.
- Remove the duplicated headings and `TBD.` fields; keep one copy of each section.

Integrated repair revision: `a32d84ab8c1c109dcc6d073ad2d05728f296a126`.
The owning Feature spec records source, design and verification review.
