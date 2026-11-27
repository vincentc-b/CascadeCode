---
id: task_049_004_002
title: Verify UTF-8 detail cursor refusal and positive continuation
tier: task
status: completed
parent: feat_049_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 522edf7a927f7bb8cbbd302318d1272ce1e8e5f9
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify UTF-8 detail cursor refusal and positive continuation

## Parent Feature

[feat_049_004](../../features/2_active/feat_049_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope
Finish the existing UTF-8 detail cursor correction in `cascade/war_room/transcript_pages.py` and loopback API coverage. The candidate boundary check is already present in the integrated Feature checkout; validate it against the public behavior before changing code.

## Acceptance criteria
- A cursor offset inside a multibyte UTF-8 character returns typed HTTP 400 `invalid_request` through the existing detail route. Use an oversized emoji body and caller-edited opaque cursor to exercise the actual loopback route.
- Normal multibyte chunks reconstruct the exact original body. Every successful incomplete response advances the byte offset and yields a new cursor; completed reads terminate. Bind graph, message, incarnation and digest; changed identity restarts through the existing typed contract.
- Preserve read-only GET, no JSONL/index opening on GET, 64 KiB detail chunks, 1 MiB source budget and 256 KiB response limit. Exercise the existing route/header/error/detail fixtures needed by Feature 3 without redesigning routes.
- Run focused `tests/war_room/test_transcript_pages_api.py` cases and record exact command/results, route fixture paths, source symbols and any residual gap.

## Design impact
Reconcile `cascade/war_room/DESIGN.md` and `cascade-dashboard-code`/source-contract detail node with actual behavior; give Task 3 the current-design wording and verification evidence.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
