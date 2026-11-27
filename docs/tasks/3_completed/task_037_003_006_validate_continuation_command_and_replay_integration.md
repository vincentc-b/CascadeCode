---
id: task_037_003_006
title: Validate continuation command and replay integration
tier: task
status: completed
parent: feat_037_003
children: []
depends_on:
- task_037_003_005
owners:
- swe
skills: []
parent_rev: f8c57b27b46ef155f61c6fdf31fc9fe82385b230
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate continuation command and replay integration

## Parent Feature

[feat_037_003](../../features/2_active/feat_037_003.md)

## Depends on

- task_037_003_005

## Acceptance criteria

- Exercise the command/API path for human-only authorization, Flex-only versus mixed failures, fresh inventory and revision races, unchanged plan hashes and dirty worktrees, duplicate clicks/concurrent requests in threads and separate processes, and restart before/after handoff.
- Wire the server-computed Continue without Flex control to an explicit War Room action and HTTP command endpoint. The server supplies the authenticated human principal; the request supplies the concrete failed-action ID and expected revision/fingerprint. Return the durable receipt and structured refusal or replay outcome, and reject non-human callers. Verify the browser action reaches the command and does not treat a read-only preview as authorization.
- Verify the read-only action projection derives current lifecycle, dependency and approval eligibility from server state. The authorization command must recheck those conditions from server state as well. A stale or released action must lose the Continue control even when its Flex-disabled capability check still passes.
- Verify waiver carry-forward through canonical status relocation and Task parent-pin refresh, and invalidation after an unrelated edit or independent child override.
- Exercise all four original-action adapters, including an ordinary gate refusal and event-before-kickoff ambiguity. The normal successful path has exactly one lifecycle event and one model turn.
- Fix any integration defect exposed by these checks and run the relevant repository checks. Record a concrete accepted limitation only when the feature contract permits it.

## Files likely touched

Focused command/API and dispatch integration tests; command, projection or replay wiring if a check exposes a defect.

## Implementation notes

Keep tests high-signal and avoid duplicating the pure evaluator matrix. The current read-only projection passes default lifecycle and approval booleans into eligibility; verify it against actual server state before treating the UI action as valid. There is currently no continuation button or HTTP route, although the read-only projection exists; close that delivery gap as part of the command/API integration. The current receipt claim uses a process-local lock; prove one durable claim across separate processes or add a shared lock around ledger read-modify-write.

## Skills

_(none)_

## Test plan

Run the focused continuation integration suite and relevant provider dispatch, waiver and recovery checks.

## Out of scope

Unrelated provider recovery flows or broad lifecycle refactors.
