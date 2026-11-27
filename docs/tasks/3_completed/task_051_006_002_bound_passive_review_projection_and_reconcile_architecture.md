---
id: task_051_006_002
title: Bound passive review projection and reconcile architecture
tier: task
status: completed
parent: feat_051_006
children: []
depends_on:
- task_051_006_001
owners:
- swe
skills: []
parent_rev: 75d8da3216c3660a737e43182ee4a74947d88ca2
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Bound passive review projection and reconcile architecture

## Parent Feature

feat_051_006; follow its lossless evidence bounds and pinned parent revision.

## Depends on

- task_051_006_001

## Acceptance criteria

- Bound `cascade/review.py:_review_evidence_projection` and `feature_review_views` for current registry, legacy observations, repair-request fallback and verification-postcheck fallback. Preserve supported exact string and integer generations including zero; enforce 256 UTF-8 bytes for names/string generations, 64 decimal digits for integers and 32 KiB for normalized observation. Malformed or over-limit evidence has explicit unavailable state and safe prerequisite, never empty-green, verified or falsely fresh. Keep at most twenty sorted rows and explicit omitted count.
- Board, Feature room and `GET /api/open-reviews` return the same bounded evidence. Passive GET and polling make no forge, lifecycle, repair or provider calls and do not rewrite the registry or action history.
- Focused API and production-path tests cover boundary/over-limit Unicode bytes, same-prefix identities, long string and integer generations, zero, omitted rows, unavailable persistence, legacy/fallback payloads and unchanged ordinary behavior. Assert serialized response bounds and unchanged authoritative comparisons.
- Trace `cascade/tracking.py:_review_health`, `cascade/review_health.py:_route_actionable_review_health`, `cascade/watchdog/incident_postcheck.py:_required_checks` and `cascade/feature/repair.py:mark_feature_repair_verified` for exact-head/check-generation authority and fail-closed outcomes.
- Reconcile root `DESIGN.md`, `cascade/DESIGN.md`, `cascade/watchdog/DESIGN.md` and `cascade/war_room/DESIGN.md` against the final diff, preserving single ownership of `REQ-WARROOM-REVIEW-002`. Source-link normal persistence/read and oversized/legacy refusal after restart. Inventory `cascade-landscape`, `cascade-context`, `cascade-containers` with grounded no-change reasoning for unchanged actors/runtime/store, and reconcile `cascade-supervisor-components`, `cascade-team-components`, `cascade-war-room-components`, `cascade-watchdog-code`, `cascade-dashboard-code` plus affected `cascade-war-room-http-code`, `cascade-feature-code` and `cascade-task-code`. Update native source-linked nodes only for significant new responsibilities; route Epic-owned model/contract edits through the permitted pinned publication path.
- Validate source contract, declaration kinds and ownership, bounded pinned render, context → container → component → Code Explore, Level up, deep-link restoration and representative pinned-source opening. Check stale symbols and warm artifact reuse. Record actual checks and limitations in the Task closeout.

## Files likely touched

`cascade/review.py`, `tests/war_room/test_open_reviews_api.py`, related review-health/postcheck tests, `DESIGN.md`, `cascade/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/war_room/DESIGN.md`, and permitted architecture model/contract files.

## Implementation notes

Reuse the shared projection and existing review registry/action ledger. Keep model/source links and supplemental flow aligned with implemented code. Do not treat a successful render as enough to prove Code navigation or source opening.

## Skills

_(none)_

## Test plan

Run focused review-health, postcheck and War Room API checks; record exact commands/results. Keep known lifecycle/architecture fixture failures and the full Recovery-gate timeout distinct from an isolated retry. Final Epic acceptance remains with integrated verification and publication.

## Out of scope

New store, scheduler, CI framework, dependency installation, deployment, accepted snapshot rewrite, and unrelated delivery-consumer changes.
