---
id: task_039_003_004
title: Prove blocked-to-ready lifecycle and epic acceptance
tier: task
status: completed
parent: feat_039_003
children: []
depends_on:
- task_039_003_003
owners:
- swe
skills: []
parent_rev: daa8f97b534179c83e16cc2a249a6c591d68b836
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove blocked-to-ready lifecycle and epic acceptance

## Parent Feature

[feat_039_003](../../features/2_active/feat_039_003.md)

## Depends on

- task_039_003_003

## Acceptance criteria

- Ordinary workspace-worker and server CLI startup expose the action flow only through a trusted request-scoped human identity boundary. An unauthenticated direct API request is refused even when a different request has authenticated; server-wide identity injection alone cannot grant authority.
- Ping has a bounded executor wired to the actual target environment, or returns a visible unavailable refusal without changing readiness. A normal launched War Room can complete the authorized blocked-to-ready flow.
- Manifest writes, scope review, binding comparison, and independent approval journal appends serialize across processes. A concurrent manifest change produces either a stale refusal or approval for the exact reviewed current binding; no unreviewed authority is written.
- Existing browser/API integration proves blocked → human review and per-entry approval → Ping → same-run recheck → planning readiness, plus stale/denied authority, duplicate request and restart, retained accepted work, environment mismatch, and explicit no-dependency behavior.
- The eleven epic criteria are reported against real local/container and Structurizr evidence. Any missing authorization or real execution evidence remains an explicit unpassed blocker.

## Files likely touched

TBD.

## Implementation notes

Task 002 closed the route/API path but left runtime wiring and process boundaries open. The workspace worker and server CLI currently pass neither `authenticated_human` nor `dependency_executor` to `serve()`. Do not treat a static server-wide `AuthenticatedHuman` as a request principal; every authority-granting request needs a trusted verifier. Review/approval and Ping must fail closed with useful browser feedback when the relevant trusted capability is absent. The manifest writer, approval helper, and bootstrap review still use only `process_lock`; use a shared cross-process lock or equivalent atomic compare-and-write for these paths. Preserve the operation-time installation gate.

Use the existing browser/API integration harness for blocked -> human action -> ping -> same-run recheck -> planning readiness, including denial/stale authorization, independent batch approvals and selective invalidation, duplicate requests/restart, preserved accepted work, actual environment mismatch, and explicit no-dependency flow. Verify all eleven epic_039 success criteria against slice A/B canonical records and the real local/container and Structurizr evidence from slice B. Keep host Java incompatibility, immutable container digest and bundled runtime, in-container check, and separate adapter feasibility visible. If real authorized evidence is missing, record the acceptance blocker and leave that criterion unpassed; never substitute simulated success. Avoid redundant low-level tests or new dependency installations.

## Skills

_(none)_

## Test plan

Use the existing browser/API harness for one full authorized lifecycle and refusal feedback. Add one targeted multiprocess race test for manifest updates against approval/review, and one direct API test proving request-scoped identity and default-startup refusal. Reuse slice B's real smoke artifact; report missing real evidence without installing or pulling anything.

## Out of scope

TBD.
