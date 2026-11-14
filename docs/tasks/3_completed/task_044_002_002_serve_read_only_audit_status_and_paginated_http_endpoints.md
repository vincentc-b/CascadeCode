---
id: task_044_002_002
title: Serve read-only audit status and paginated HTTP endpoints
tier: task
status: completed
parent: feat_044_002
children: []
depends_on:
- task_044_002_001
owners:
- swe
skills: []
parent_rev: a32b902814a79c002910f903bf048b3c4377c290
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Serve read-only audit status and paginated HTTP endpoints

## Parent Feature

[feat_044_002](../../features/2_active/feat_044_002.md)

## Depends on

- task_044_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Wire the bounded reader from task_044_002_001 into the War Room health routes. Acceptance: GET /api/health/audit returns snapshot state, observation/freshness/epoch, a first page of verified current incidents, aggregate coverage counts and bounded receipt/failure metadata; GET /api/health/audit/coverage and /api/health/audit/history expose filtered pages with default limit 50, max 100, epoch-bound continuation and explicit incomplete/restart/error states. Map the old fields needed by the current JavaScript client without restoring lifecycle, Git, provider, worktree, recovery-ledger or investigation scans; update its interim zero-incident wording to say no VERIFIED current incidents and incomplete coverage when appropriate. Keep POST /api/health/audit authentication, admitted/coalesced semantics and scheduling unchanged. No GET may write runtime files or dispatch scans/repairs. Preserve split product/tracking root routing and keep legacy remediation rows in history/coverage, never active.

Likely files: cascade/war_room/audit_status.py, health_routes.py, static/audit_status_ui.js only for interim truthfulness, cascade/war_room/DESIGN.md, tests/war_room/test_health_audit_routes.py and focused client cases. Test repeated concurrent GETs with probe/write spies, absent/stale/corrupt snapshots, a later current blocker after historical failures, timeout/deferred coverage, filter/epoch/page errors, split roots and manual POST. Demonstrate response/read budgets and record warm local GET p95 on a representative 10,000-attempt fixture (environment and measurement), without a flaky latency assertion as sole evidence. Do not redesign the full UI, change audit-lane admission, implement recovery, or remove durable history.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
