---
id: task_044_002_001
title: Build bounded epoch-pinned audit projection reader
tier: task
status: completed
parent: feat_044_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: f04d2a5439b313016d5f332cb0ba1a02d7fb9d29
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Build bounded epoch-pinned audit projection reader

## Parent Feature

[feat_044_002](../../features/2_active/feat_044_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the bounded schema-2 projection consumer boundary. Acceptance: producer publishes compact row totals and coverage aggregates (status/reason) in each immutable manifest; the aggregate is bounded and validated, and does not require reading history pages on GET. Add a consumer reader that reads only the current pointer, one manifest, and requested current/coverage/history pages using regular-file no-follow bounded opens. Never call read_projection_manifest from this reader because it validates the full epoch. Validate schema, page kind/epoch, product and tracking identity, timestamps and freshness; missing/corrupt/incompatible/wrong-root data returns typed pending/unknown. Return at most 100 rows, 1 MiB read bytes and 256 KiB serialized bytes, with explicit incomplete/continuation. Cursor binds section, epoch, page/row offset and normalized exact work_id/owner/status plus UTC occurrence-time filters; reject malformed or mismatched cursors and never accept a path from a cursor. Preserve source_ref and detail_truncated without raw-ledger lookups. Later published epochs must invalidate or explicitly restart an old cursor. Keep producer publication and raw ledgers unchanged.

Likely files: cascade/watchdog/audit_projection.py, a focused reader under cascade/war_room/, cascade/watchdog/DESIGN.md, cascade/war_room/DESIGN.md; focused tests in tests/watchdog/test_audit_projection.py and tests/war_room/. Test missing/stale/corrupt/incompatible pages, wrong product/tracking roots, concurrent pointer change, filters across pages, legacy provenance, a record too large for inline detail, and the read/response ceilings on 10,000 varied attempts. Do not wire HTTP routes, alter audit scheduling or repair authority, add dependencies, or rewrite source ledgers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
