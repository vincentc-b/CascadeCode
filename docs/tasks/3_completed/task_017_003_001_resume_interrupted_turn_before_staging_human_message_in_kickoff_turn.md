---
id: task_017_003_001
title: Resume interrupted turn before staging human message in _kickoff_turn
tier: task
status: completed
parent: feat_017_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d9142cce5835422523303885d043273bfd4d0ecf
created: '2026-10-23'
updated: '2026-10-23'
---
# Resume interrupted turn before staging human message in _kickoff_turn

## Parent Feature

[feat_017_003](../../features/2_active/feat_017_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Scope item (c) of feat_017_003.

## Change
In `_kickoff_turn` (`cascade/workspace/kickoff.py`), for `comment` / `human_message` jobs: when `_graph_has_inflight_turn(...)` is true, first resume the interrupted turn via `_invoke_role_turn` with no new input, BEFORE `_stage_human_message`. Then stage the message and run the job's own turn as usual.

- Use the existing `_graph_has_inflight_turn` (non-empty `snapshot.next` AND a role message on the thread) as the only definition of interrupted. Do NOT use `snapshot.next` alone.
- No changes to queue format, checkpoint schema, LangGraph topology, or `seed_*_role_models`.

## Acceptance
One scenario test on the real `SqliteSaver` harness (`tests/harness/queue_delivery.py`), extending `tests/workspace/test_feat_017_queue_cursor_race.py`: a `comment` job landing on an interrupted checkpoint resumes the cut-off turn exactly once, then stages the message and runs exactly one more turn; the human message is present in the final checkpoint.

No extra unit tests beyond this scenario.

## Sequencing
Must merge before feat_017_002 starts (restart convergence relies on this guard).

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
