---
id: task_049_003_003
title: Prove recovery progress and transcript behavior through operational journeys
tier: task
status: completed
parent: feat_049_003
children: []
depends_on:
- task_049_003_001
- task_049_003_002
owners:
- swe
skills: []
parent_rev: 1c7fbea950c3a17a9b8e860655c7ac7dfc090df5
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove recovery progress and transcript behavior through operational journeys

## Parent Feature

[feat_049_003](../../features/2_active/feat_049_003.md)

## Depends on

- task_049_003_001
- task_049_003_002

## Acceptance criteria

- Bind real source traces to Feature 4 handoff `a3d4a42b3df92a553206c300c42142600183eaef`, `tests/war_room/fixtures/recovery_progress_v1_epic_044.json`, `tests/war_room/test_transcript_pages_api.py` and `tests/recovery_progress/test_transcript_milestones.py`; distinguish committed-notification fast path from bounded drain/replay.
- Exercise the held-final-reply timeline at real notification → publication → HTTP → Chromium boundaries. Assert the committed milestone anchor appears before the authored reply; preserve receipt/action/generation identity and prove competing incidents, ordinary append high-water, restart incarnation and positive multibyte detail continuation.
- Record source and response bytes against 1 MiB and 256 KiB ceilings, 100-row bound, and measured warm board/room navigation. Report scoped browser evidence separately from Feature 4's broader documentation-refresh assertion failure.
- Diagram impact: trace the normal and pending/replay flows across `cascade-context`, `cascade-containers`, `cascade-war-room-components`, `cascade-supervisor-components`, `cascade-dashboard-code`, `cascade-watchdog-code` and affected Task/Workspace/Teams code views; send actual source deviations to the owning design/C4 task.

- Reproduce 03:58:01 queued, 03:58:10 acknowledged and 04:02:25 started while final role reply is held; prove start fast path and supervisor replay at supported HTTP/UI boundaries.
- Cover queued idle, acknowledgement, investigating versus executing, waits, dead/expired/inaccessible owner, retry/exhaustion, generation change and authoritative verification; queued live worker without invocation token remains non-executing.
- Exercise pending delivery/import, competing incidents, older authored statements, refresh/navigation, service and worker restart, and two real writer processes; one milestone per material transition.
- Verify progress/chat GET source/response/row bounds and absence of provider, Git, process, checkpoint, raw-history probes and paid turns; measure representative warm navigation.

## Files likely touched

tests/war_room and focused recovery_progress integration fixtures; production code only for a demonstrated acceptance defect.

## Implementation notes

Implement Task 3 in the feature spec: deterministic 03:58:01/03:58:10/04:02:25 timeline with held final reply, start fast path and supervisor replay, supported HTTP/Chromium scenarios, restarts and two-process dedupe, read-only GET budgets, exact milestone count, and measured warm navigation evidence.

## Skills

_(none)_

## Test plan

Focused API and Chromium journeys with real publication/notification and measured bytes/timing.

## Out of scope

No full repository suite or artificial prewritten-only UI proof.
