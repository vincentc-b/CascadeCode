---
id: task_044_001_004
title: Integrate projection production with audit and recovery handoff
tier: task
status: completed
parent: feat_044_001
children: []
depends_on:
- task_044_001_003
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
# Integrate projection production with audit and recovery handoff

## Parent Feature

feat_044_001 (frontmatter pins the current parent revision); epic_044's existing recovery/approval authority and producer acceptance apply.

## Depends on

- task_044_001_003

## Acceptance criteria

- Scheduled and authenticated manual passes use the existing single workspace claim and producer, coalesce duplicate admissions, preserve the periodic deadline on manual runs, and retain one overdue pass on restart. Projection publication and receipt order cannot expose a partial generation.
- Recovery handoff and owner investigations use exact work/generation evidence, run after releasing audit/lifecycle locks, and preserve existing finite cooldown, acknowledgement and approval gates. Repeated browser reads or projection refreshes do not dispatch any investigation. Request delivery and `reported_fixed` remain follow-up state, not verified resolution.
- Every repair/admission path re-reads canonical evidence and rejects an obsolete generation even if a cached projection still says current. Changed, deleted or rerouted work stays pending or is reclassified using fresh evidence.
- Producer integration tests reproduce slow first historical item followed by a new current blocker, repeated generations, legacy incomplete rows and completed work with outstanding publication. Tests cover restart, manual audit, concurrent admission, split product/tracking roots and no repeated repair side effects.
- Demonstrate the 100-candidate, 60-second, two-second per-candidate ceilings on a representative 10,000-attempt ledger containing varied owners/generations and malformed rows. Record environment, measured producer work and any limitation; do not rely on timing assertions alone.

## Files likely touched

`cascade/watchdog/audit_lane.py`, `cascade/watchdog/audit_recovery.py` or `reservations.py` only if a fresh-authority regression requires a fix, `cascade/watchdog/audit_agent_lane.py`, and focused `tests/watchdog/` integration/performance fixtures.

## Implementation notes

The existing receipt, failure record, outbox and claim are the scheduling/recovery boundary. Keep the healthy pass receipt-only. Reuse existing investigation cooldown/case deduplication; avoid a new scheduler, queue or repair adapter. Feature 002 owns read-only GET budgets and feature 003 owns live War Room evidence.

## Skills

_(none)_

## Test plan

Run focused watchdog audit, recovery and investigation suites. Add high-signal integration tests for exact-generation refusal and coalescing, plus a separate measured large-ledger benchmark/evidence artifact with environment and counts.

## Out of scope

Dashboard GET/API, browser UI, source-ledger edits, changing recovery policy or requiring new dependencies.
