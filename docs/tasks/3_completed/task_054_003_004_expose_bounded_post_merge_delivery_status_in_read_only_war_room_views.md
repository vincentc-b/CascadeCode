---
id: task_054_003_004
title: Expose bounded post-merge delivery status in read-only War Room views
tier: task
status: completed
parent: feat_054_003
children: []
depends_on:
- task_054_003_003
owners:
- swe
skills: []
parent_rev: f4683ee06383f5391cb26d9654323a7fc1b4092c
created: '2026-11-28'
updated: '2026-11-28'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose bounded post-merge delivery status in read-only War Room views

## Parent Feature

[feat_054_003](../../features/2_active/feat_054_003.md)

## Depends on

- task_054_003_003

## Acceptance criteria

1. Extend existing persisted review/delivery projections and War Room GET/dashboard views to show distinct prospective validation, accepted merge SHA, exact merge CI state, local/remote trunk heads and sync result, physical board status, repair owner/prerequisite and verified closure. Normal and failure views carry exact revision and actionable next step without conflating pending, unavailable and failed states.
2. Read only bounded persisted producer projections in GET/polling. No Git fetch, forge request, CI validation, provider turn, lifecycle mutation or unbounded ledger scan on the read path. Producer generation deduplication/backoff avoids repeated unchanged model turns and validation.
3. Focused API/browser tests prove normal and failure display, stale generations, malformed bounded fallback and repeated reads without side effects; retain current review owner and URL.
4. Reconcile cascade/war_room/DESIGN.md and cascade/watchdog/DESIGN.md producer interface. Update cascade-war-room-components, cascade-dashboard-code, cascade-war-room-http-code and affected cascade-watchdog-code in pinned model/views/contract. Check source symbols/kinds, navigation, render and bounded warm reuse; record all-level impact and normal/failure traces.

## Files likely touched

cascade/review.py; cascade/war_room/; cascade/watchdog/; cascade/war_room/DESIGN.md; cascade/watchdog/DESIGN.md; tests/war_room/test_open_reviews_api.py; tests/war_room/; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}.

## Implementation notes

Implement the focused contract above using the existing adapters, receipts and owner boundaries.

## Skills

_(none)_

## Test plan

Run the focused real-Git, scripted-forge and architecture checks named above; record exact commands, results and gaps.

## Out of scope

A second observation scheduler or store.
