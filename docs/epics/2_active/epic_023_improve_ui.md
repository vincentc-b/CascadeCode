---
id: epic_023
title: Improve UI
tier: epic
status: active
parent: null
children:
- feat_023_001
- feat_023_002
- feat_023_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-23'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-sol
  epic_architect: gpt-6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Improve UI

## Intent

Make the War Room board stable and central to the page, keep its supporting context easy to reach, let users set useful panel widths on different screens, and let users prioritize backlog features by dragging them. Improve the time to a usable board and the speed at which changes appear.

### Success criteria

- On wide screens, the In flight / chat context is left of the board, the board occupies the center, and the existing utility sidebar remains on the right. Board width does not jump when board data refreshes or cards change.
- Users can resize the three top-level panels within sensible bounds. The choice survives a reload on the same browser; a reset restores usable defaults. The page uses available viewport width rather than the present 1400px cap.
- At narrower widths the panels reflow without horizontal page overflow or hidden controls. The board remains usable, including selection, actions, chat, and backlog ordering.
- Backlog feature cards can be dragged to reorder priority within their epic. The resulting order is durable, is shared by board readers, survives refresh/reload, and is shown consistently wherever that backlog is rendered. An invalid or stale reorder has a clear failure and does not silently replace newer order.
- The initial board is usable within 2 seconds in the agreed local benchmark; ordinary board actions and incoming state changes provide prompt visible feedback. A reproducible before/after performance review identifies and fixes the material bottlenecks rather than adding speculative caching.

## Macro-architecture

The War Room remains a server-rendered HTML shell with CSS and plain JavaScript in cascade/war_room. Its three existing regions are room-panels (context), war-room-board (board), and side-panels (utilities). Change the layout and interaction layer around those regions without moving their ownership or changing the board's epic/feature/task lens semantics. Desktop reading order and keyboard navigation must follow the visible left-to-right order. At narrow widths, use a clear stacked layout with the board prominent.

Persist panel widths as a presentation preference scoped to this browser and page, with versioned or validated values so stale or impossible widths fall back to defaults. Clamp widths when the viewport changes. Resizing must not mutate board data or fight the 3-second board polling render.

Feature priority is shared domain state, keyed by parent epic and feature ID, not a browser preference. Add a guarded, atomic War Room reorder command and project its canonical order into GET /api/board. Accept an explicit ordered list or move intent only for features still in the same backlog epic, validate membership and concurrency against the current board, and return the accepted canonical order. New backlog features append after ranked peers; missing or departed features are ignored/compacted on read. Keep existing feature dependency/readiness and explicit dispatch rules unchanged. The board's feature lens consumes this order without sorting again by ID.

The performance work measures navigation to first usable board, board API time, render cost, and action-to-visible-update on a representative local board. Optimize the slow path found by measurement, including backend work repeated on every poll and unnecessary full DOM replacement if those are significant. Preserve fresh lifecycle status and current polling/error behavior.

## Cross-module constraints

- Board/feature state and order must be resolved from the same current merged board snapshot used by the War Room. Writes require the usual process and storage guards; do not edit feature docs solely to express a visual reorder.
- Reordering changes priority display only. It must not bypass dependencies, plan approval, execution caps, or trigger feature dispatch. Boss dispatchable feature presentation may use the same order where it shows a queue.
- Existing row actions, selected epic/feature lens, collapsed completed columns, return-to-backlog flow, chat, and sidebar actions must continue to work after layout or rerender changes.
- Provide a non-drag way to move a focused backlog feature up or down, with clear accessible labels and focus retention. Do not let a drag starting on row action controls invoke a row action.
- Avoid extra network requests or expensive work per poll merely to maintain layout preferences or priority order. Failures should retain the last confirmed server order and report the problem to the user.

## Core dependencies

- Existing War Room template, war_room.css, war_room.js, board_focus.js, GET /api/board serialization, and board state/merge snapshot APIs.
- The priority command needs a durable store and validation under the same concurrency conventions used by War Room mutations. Its exact persistence module is an implementation choice for the feature architect as long as it is shared across clients and survives restarts.
- Performance review needs a repeatable local seed/fixture and browser timing plus server timing; use the same fixture before and after. Do not set a target based on network or third-party services outside this app.

## Feature breakdown

- **feat_023_001 — Centered responsive War Room layout and resizable panels.** Put context left, board center, utilities right; use the viewport; add clamped, persistent resize controls and reset; reflow at tablet/mobile widths. Acceptance: wide, medium, and narrow viewport checks; no width jump during board poll, selection, or completed-column expansion; controls remain accessible.
- **feat_023_002 — Durable backlog feature priority.** Add canonical per-epic order and a guarded reorder API; render ordered backlog feature cards with drag/drop and keyboard move controls; keep it coherent after feature creation, dispatch, cancellation, refresh, and concurrent edits. Acceptance: ordering survives reload and another client, is limited to backlog peers in one epic, and stale/invalid writes are refused visibly. Can proceed in parallel with feat_023_001.
- **feat_023_003 — War Room latency review and targeted fixes.** Establish a repeatable baseline, identify the dominant board load and refresh costs, fix the material causes, and record before/after timings. Acceptance: p95 navigation-to-usable-board under 2 seconds on the documented local fixture and machine class across at least 20 runs; no regression in action feedback or lifecycle freshness. Start measurement early, then finish against feat_023_001 and feat_023_002.

## Open questions

- The exact priority persistence format and API concurrency token are for the feature architecture to choose while preserving the contract above.
- If the baseline reveals that the 2-second target is impossible on the representative fixture without a larger data-path change, record the measurements and propose a scoped amendment before weakening the target.

## Decision log

- 2026-10-23 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-05 · Epic Manager · **Feature breakdown**
  Chose Backlog feature priority is a durable order scoped to one epic; reordering changes presentation and queue order but does not trigger or bypass dispatch.
  Rationale: The request asks users to prioritize backlog features. Shared durable order makes that priority consistent across refreshes and clients, while existing dependency and human dispatch controls retain their meaning.
  Honors: Intent and success criteria for backlog drag and drop.

- `dec_002` · 2026-11-05 · Epic Manager · **Macro-architecture**
  Chose Use a desktop context-board-utilities layout with browser-scoped resizable panel widths and responsive fallback.
  Rationale: This directly addresses the unstable board width and varied screen sizes without adding shared layout state or changing board selection behavior.
  Honors: Intent and success criteria for layout, resizing, and screen sizes.

- `dec_003` · 2026-11-05 · Epic Manager · **Core dependencies**
  Chose Measure the existing War Room path before changing it and verify p95 navigation-to-usable-board below 2 seconds on a documented local fixture after the UI features land.
  Rationale: The brief explicitly requests a performance review and a less-than-2-second page load; a shared fixture and before/after measurements make that goal testable without speculative optimization.
  Honors: Intent and success criteria for low latency and page load.
## Amendment log

_(none)_
