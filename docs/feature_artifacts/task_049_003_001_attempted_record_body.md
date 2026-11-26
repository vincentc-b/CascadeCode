# Task 1 attempted record body and lifecycle refusal

The completed Task 1 board record still has `TBD` acceptance, file, test and
out-of-scope sections. The exact body submitted to Cascade MCP `revise_task`
for `task_049_003_001` is preserved below, including its incorrect Parent
Feature link. Its lifecycle metadata and frontmatter remain authoritative in
the board. This is historical evidence, not a corrected proposal.

```markdown
# Present current recovery progress on board and beside Historical

## Parent Feature

[feat_049_003](../../features/2_active/feat_049_003.md)

## Depends on

None.

## Acceptance criteria

- Consume the same safe progress semantics on the board and beside Historical, retaining work, graph, action, generation, entry and projection revision identity. Show ordered concurrent incidents and continuation, supported state/stage, owner, occurrence or unknown time, observation freshness and lag, attempt, prerequisite, safe next step, safe review/action link and committed milestone references.
- Keep pending, incomplete, expired and inaccessible evidence visible. A queued live worker without an invocation token is not executing. Publication success remains verification pending until an authoritative postcheck.
- Reject older asynchronous responses and prior-graph responses. Handle typed `400 invalid_request` and `409 revision_changed` with a safe restart. Render text safely and use only allowlisted local URLs.
- Reconcile the War Room design and `cascade-war-room-components`, `cascade-dashboard-code` and affected `cascade-war-room-http-code` source symbols. Preserve producer requirements and decisions in `cascade/recovery_progress/DESIGN.md`.

## Files likely touched

`cascade/war_room/recovery_progress.py`, `cascade/war_room/static/war_room.js`, `cascade/war_room/static/war_room.css`, `cascade/war_room/templates/war_room.html`, `cascade/war_room/DESIGN.md`, the Dashboard C4 model/views/source contract and focused War Room tests.

## Implementation notes

Merged implementation `5dc6e60e680f9e49f1f7f4c1fc9976fb3ddc79c5` adds a compact board primary from the same progress projection, a persistent room panel, ordered concurrent entries, safe text/local links and a Dashboard Code node. Task 2 owns the remaining room-panel refresh during an already-open room and stable versioned-transcript milestone anchors; Task 3 owns the held-final-reply operational proof.

## Skills

_(none)_

## Test plan

On the integrated feature branch, `python -m pytest -q tests/war_room/test_recovery_progress_api.py tests/war_room/test_ui_render.py -k 'recovery_progress or recovery_incident or get_home'` passed 11 cases; `python -m pytest -q tests/workspace/test_c4_source.py` passed 14. `node tests/war_room/recovery_progress_current_cases.mjs` and `git diff --check b47b1b78..5dc6e60e` passed. This is focused source/UI evidence, not a rendered Code navigation or integrated operational acceptance claim.

## Out of scope

Recovery producer state, transcript storage and room paging, durable milestone publication, the writer-contention repair, and final integrated operational acceptance.
```

The Feature team called Cascade MCP `revise_task` with this exact body for
`task_049_003_001`. It returned the lifecycle refusal:
`task_049_003_001 cannot be revised while completed`. The feature spec retains
the delivery evidence; this handoff does not change the canonical Task record.
