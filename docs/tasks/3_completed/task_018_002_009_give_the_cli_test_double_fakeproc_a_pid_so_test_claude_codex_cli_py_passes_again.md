---
id: task_018_002_009
title: Give the CLI test double _FakeProc a pid so test_claude_codex_cli.py passes again
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: a7a3d66ae303589e6f6347fa305521fb683fc89e
created: '2026-10-23'
updated: '2026-10-23'
---
# Give the CLI test double _FakeProc a pid so test_claude_codex_cli.py passes again

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
Fix the regression from task_018_002_003 (feature dec_023, dec_024): three tests in `tests/agent/test_claude_codex_cli.py` fail on `feat/feat_018_002` with `AttributeError: '_FakeProc' object has no attribute 'pid'`, because 003 made `cascade/agent/cli_common.py` read `proc.pid` to call `set_current_turn_pid`.

## Change
- In `tests/agent/test_claude_codex_cli.py`, add `self.pid = None` to `_FakeProc.__init__`. Use `None`, not a made-up number, so the turn registry can never SIGTERM a real process.
- Touch nothing else. No production change (real `asyncio.subprocess.Process` always has `pid`), no new test.

## Acceptance
- `pytest tests/agent/test_claude_codex_cli.py` passes all 12 tests (it passes at base `47f19ba`).
- The diff is that one line in that one file.

## Out of scope
- Any change to `cascade/agent/cli_common.py` or the turn registry.
- The fake-provider gate (task_018_002_008).

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
