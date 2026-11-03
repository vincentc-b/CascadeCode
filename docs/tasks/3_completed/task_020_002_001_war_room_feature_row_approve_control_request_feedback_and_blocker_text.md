---
id: task_020_002_001
title: 'War Room feature row: approve control, request feedback, and blocker text'
tier: task
status: completed
parent: feat_020_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: b08df021b3402105acba63c4d9a32cdb193dd8aa
created: '2026-10-23'
updated: '2026-10-23'
---
# War Room feature row: approve control, request feedback, and blocker text

## Parent Feature

[feat_020_002](../../features/2_active/feat_020_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Edit only `cascade/war_room/static/war_room.js` feature rows. Build against the readiness contract merged by feat_020_001 (`cascade/feature/readiness.py::compute_feature_readiness`, serialized by `cascade/war_room/serialize.py::feature_readiness_to_dict`).

- Render nothing (no control, no blocker text) when `readiness` is absent on the row.
- When `readiness.approved` is false: show the "Awaiting feature approval" status and an "Approve feature" button that POSTs `/api/approve_feature` with `{id}`. Reuse the `actionButton`/`dispatch` helpers and follow the epic "Approve plan"/"Approved" pattern.
- While the request is in flight, disable the button and show a pending state. On success, show a confirmation and refresh the board. On a 409 or network error, show the server message in the existing toast/error area and re-enable the button.
- When approved, render `readiness.blockers` as human-readable text. Match on the prefix before the first `:`. `unmet_deps:<ids>` lists the dependency ids. `dispatch_base_unavailable:<reason>` shows "stacked base unavailable" with the reason. Give readable labels to `feature_awaiting_merge`, `sibling_blocked`, `review_threads_blocking`, `epic_inactive`, and `not_in_backlog`. Never render `not_approved` as a blocker, because the status already covers it. Render unknown codes verbatim. Render nothing extra when there are no blockers.
- Add no client-side gate logic: render only what the server sends. Make no backend changes.

Done when: the control and blocker text appear as described against the live board payload.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
