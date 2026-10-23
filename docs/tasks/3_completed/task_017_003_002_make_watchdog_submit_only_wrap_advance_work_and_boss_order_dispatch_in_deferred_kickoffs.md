---
id: task_017_003_002
title: 'Make watchdog submit-only: wrap advance_work and boss-order dispatch in deferred_kickoffs()'
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
# Make watchdog submit-only: wrap advance_work and boss-order dispatch in deferred_kickoffs()

## Parent Feature

[feat_017_003](../../features/2_active/feat_017_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Scope item (b) of feat_017_003.

## Change
Wrap in `deferred_kickoffs()` (from `cascade/workspace/kickoff.py`):
- `advance_work(repo)` in `watchdog_tick` (`cascade/watchdog/loop.py`), plus the second `advance_work` call near line 189.
- The boss-order `dispatch_feature` / `dispatch_task` calls in `cascade/boss/orders.py`.

Today `dispatch_*` -> `_boot_after` -> `kickoff_turn` runs a full model turn inline on the watchdog thread. After this change the watchdog thread must never hold or wait on `_graph_lock`; turns run on the kickoff drain thread.

`invoke_tool` stays lock-free. No queue/checkpoint/topology changes.

## Acceptance
- One test: `watchdog_tick` with a dispatchable item returns without invoking a model turn on the calling thread (counting fake turn runner; the turn runs on the kickoff drain thread).
- Existing `tests/watchdog/test_watchdog.py` monkeypatches of `deliver_queue_kickoffs` / `kickoff_graph_queue_event` keep working unchanged.

## Risk
If the wrapper changes observable ordering that existing watchdog tests depend on, stop and raise it to feature_lead for an epic amendment. Do not drop the wrapper or rewrite the tests to hide it.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
