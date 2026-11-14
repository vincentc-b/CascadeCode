---
id: task_044_001_002
title: Rotate audit candidates fairly and isolate observations
tier: task
status: completed
parent: feat_044_001
children: []
depends_on:
- task_044_001_001
owners:
- swe
skills: []
parent_rev: b06beabcf813e4cddb4d312cd80cd95f29ffd5af
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Rotate audit candidates fairly and isolate observations

## Parent Feature

feat_044_001 (frontmatter pins the current parent revision); epic_044's audit scheduling and authority limits apply.

## Depends on

- task_044_001_001

## Acceptance criteria

- Select at most 100 unique typed work/root identities per pass from nonterminal/recent work and older unresolved references. Keep independent persistent positions for ongoing and historical pools, rotate Task/Feature/Epic within each, and reserve at least one historical admission in four when both pools are nonempty.
- A slow, malformed or unavailable candidate records a distinct pending/retry reason, advances its exact continuation and permits later candidates in the same or subsequent bounded pass. Retain multiple source generations for one work while observing its work/root only once per pass.
- Enforce at most two seconds for one observation including Git/subprocess I/O and at most 60 seconds for selection, observation and coordination together. A completed partial page records deferred coverage; failed, busy or cancelled passes do not falsely advance last completed time.
- Reuse a read-only merged board snapshot during one pass where safe. Never pass that cache to recovery/admission. Preserve split tracking/product routing and cross-process workspace claim semantics.

## Files likely touched

`cascade/watchdog/audit.py`, `cascade/watchdog/audit_lane.py`, and focused `tests/watchdog/test_audit_candidates.py` / `test_audit_lane.py`.

## Implementation notes

The current selector rotates only tiers and the current lane passes all remaining time to each observer. Version or decode old opaque cursors safely. Keep the existing receipt compact and restart-safe. Pass-local state may live in the observer process but must be invalidated before any repair admission.

## Skills

_(none)_

## Test plan

Focused tests with more ongoing than historical candidates, a slow first historical item, a later current blocker, malformed work, duplicate references, timeout/cancellation, worker restart and split roots. Assert fairness and exact continuation without a wall-clock latency assertion.

## Out of scope

Projection file publication, dashboard GET, browser UI and changing repair/approval gates.
