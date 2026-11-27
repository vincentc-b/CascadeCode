---
id: task_015_002_001
title: Implement epic planning-readiness UI
tier: task
status: completed
parent: feat_015_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e5c158163561b8cca5ee4a668f6ee14a9a0b2936
created: '2026-10-24'
updated: '2026-10-24'
---
# Implement epic planning-readiness UI

## Parent Feature

[feat_015_002](../../features/2_active/feat_015_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Consume the server-provided planning state, valid sign-offs, approval capability, and disabled reason in the existing epic plan surface. Keep the plan visible; show an accessible Planning in progress state and semantically disabled Approve plan control with its reason until approval is allowed; switch to a non-color-only Ready for review treatment and enable approval after both current-revision sign-offs. Respect reduced-motion preferences. On stale approval rejection, retain the plan, present the actionable server error, and refresh readiness through the existing data flow. Do not add notifications, presence tracking, or redesign the viewer.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
