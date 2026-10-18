---
id: task_029
title: War Room amendment pane
tier: task
status: completed
parent: feat_006
children: []
depends_on:
  - task_027
  - task_028
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-10
updated: 2026-10-10
---

# War Room amendment pane

## Parent Feature

[feat_006](../../features/3_completed/feat_006_amendment_protocol.md) — Amendment protocol.

## Depends on

- task_027 — `AmendmentProposed`, sidecar paths, war_room amendment toasts
- task_028 — `resolve_amendment` accept/reject/revise

## Acceptance criteria

- Replace the disabled `#amendment-stub` panel in `cascade/war_room/templates/war_room.html` with feat_003 amendment chrome: collapsible pane listing **pending** amendments for the active epic (`list_pending_for_epic`), split view showing unified diff (left/right or before/after per existing CSS patterns), and **Accept**, **Reject**, **Revise** actions.
- **Revise** collects `revised_text` (textarea) and optional `note`; **Reject** collects optional `note` as reason.
- HTTP API (localhost only, same server as feat_003):
  - `GET /api/amendments?epic_id=` → JSON list of pending amendments (amd_id, feature_id, section, diff_path, rationale summary).
  - `GET /api/amendments/{amd_id}/diff` → raw diff markdown/text for pane.
  - `POST /api/amendments/{amd_id}/resolve` with JSON `{ "decision": "accept"|"reject"|"revise", "note": "...", "revised_text": "..." }` → invokes `resolve_amendment` with active epic context; returns `{ "epic_rev": "<sha>|null" }`.
- `cascade/war_room/static/war_room.js` polls or refreshes pane on amendment toasts (`kind: amendment` from `/api/toasts`); opening toast focuses pane and selects amendment.
- `cascade/war_room/toasts.py`: if needed, map additional Toast payload shapes for amendment links (minimal diff from task_010 behavior).
- `tests/war_room/test_amendments_pane.py`: HTTP tests with test client — list pending, resolve accept/reject/revise call through to epic tool (mock or temp repo with task_026–028 fixtures); 404 for unknown amd_id.
- Manual check (document in test module docstring): run War Room locally, propose from feature test harness, see toast + diff + accept updates board view.

## Files likely touched

- `cascade/war_room/templates/war_room.html` (edit)
- `cascade/war_room/static/war_room.js` (edit)
- `cascade/war_room/server.py` (edit — routes)
- `cascade/war_room/views.py` and/or `cascade/war_room/serialize.py` (edit if board view needs amendment badge)
- `cascade/war_room/toasts.py` (edit, only if mapping gap)
- `tests/war_room/test_amendments_pane.py` (create)

## Implementation notes

Wire to existing feat_003 stack only — no new frontend framework. Call into `cascade.epic.amendments.resolve_amendment` (or thin war_room service wrapper) with repo root from server. Human operator is authorized to resolve; no separate Boss gate for MVP. Do not reimplement diff generation or store writes in war_room — read via `cascade/amendments/store`. Feature `ack_amendment` remains a graph tool (not War Room) per dec_006; pane may show `revise_pending` state read-only with copy directing operator to Feature room if needed.

**Must NOT touch:** `cascade/amendments/store.py` / `diff.py` internals (public API only), `cascade/feature/amendments.py` propose logic, `cascade/epic/amendments.py` resolve implementation (except import/call), `mint_task`, watchdog loop.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/war_room/test_amendments_pane.py -q`

Optional manual: `python3 -m cascade.war_room` (or project entrypoint) + feature propose fixture.

## Out of scope

- Feature graph `ack_amendment` UI (Feature room only / tool)
- New toast transport or non-localhost binding
- Auto-accept or batch-resolve
