---
id: task_044_001_003
title: Publish atomic current coverage and history projections
tier: task
status: completed
parent: feat_044_001
children: []
depends_on:
- task_044_001_001
- task_044_001_002
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
# Publish atomic current coverage and history projections

## Parent Feature

feat_044_001 (frontmatter pins the current parent revision); epic_044's projection, history and freshness contract applies.

## Depends on

- task_044_001_001
- task_044_001_002

## Acceptance criteria

- Producer atomically publishes one immutable schema-2 epoch and swaps a small `current.json` pointer only after all manifest/current/coverage/history pages are complete. Interrupted or invalid publication leaves the prior epoch readable and records pending/failure evidence.
- Current rows require a fresh matching authoritative generation and failure class. Older generations become superseded only on later authoritative evidence. A healthy classification resolves only when the corresponding obligation is satisfied; completed work with publication or integration outstanding remains current/pending as evidence dictates.
- Coverage persists across passes/restarts with last attempted/successful verification, explicit timeout, corruption, deferred-by-budget, missing, deleted, rerouted and stale reasons, plus next scheduled attempt. A stale prior observation remains visible with its timestamp but loses the current-verified label.
- History preserves every readable attempt and legacy/unverifiable source reference; it does not rewrite recovery ledgers. Use bounded pages with at most 100 rows, a serialized byte ceiling and safe references for oversized records. Include product/tracking identities and source revision/failure markers in the manifest.
- Freshness is `last_verified_at + 2 * interval_seconds + 60 seconds`. A healthy pass with no material projection change keeps the existing receipt-only silence rule.

## Files likely touched

`cascade/watchdog/audit_projection.py`, `cascade/watchdog/audit_lane.py`, focused `tests/watchdog/` projection and restart tests.

## Implementation notes

Publish under the canonical product root's ignored runtime directory. A reader pins one epoch; neither a partial epoch nor a mixed generation may be exposed. Bound source ingestion within the pass ceiling; classify a source too large to ingest as coverage pending. Keep source references opaque and safe for feature 002.

## Skills

_(none)_

## Test plan

Focused producer tests for repeated generations, legacy/malformed rows beside valid rows, completed publication obligation, missing/deleted/rerouted work, stale/corrupt/missing epoch, interrupted pointer swap, restart and source-byte preservation.

## Out of scope

HTTP handlers, browser UI, raw-history compaction and repair-policy changes.
