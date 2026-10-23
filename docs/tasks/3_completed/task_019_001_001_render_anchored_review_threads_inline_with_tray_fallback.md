---
id: task_019_001_001
title: Render anchored review threads inline with tray fallback
tier: task
status: completed
parent: feat_019_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 6c7a79bf70f2e6c957204098846957c2438ec92d
created: '2026-10-22'
updated: '2026-10-22'
---
# Render anchored review threads inline with tray fallback

## Parent Feature

[feat_019_001](../../features/2_active/feat_019_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the epic/feature viewer reconciliation path described by feat_019_001.

Scope:
- Group ordered comments into root threads and route each root through the existing anchor-placement/relocation result.
- On epic and feature pages, create one managed inline container after each resolved canonical source block and append matching threads in API order.
- Render whole-plan and safely unplaceable roots once in the existing bottom review tray; retain current task-page behavior.
- Reuse the same reconciliation after load, poll, successful root/reply post, and resolve.
- Preserve replies, lifecycle labels and outdated styling, resolve/reply controls, unrelated reply drafts, focus/accessibility behavior, live-region announcements, and API-authoritative mutation handling.
- Add only the CSS needed for readable inline placement and supported narrow widths without horizontal scrolling.

Implementation constraints:
- Do not change comment schemas or API contracts.
- Maintain a render-local emitted-thread guard so no root is duplicated.
- Populate a per-block container as a group rather than inserting individual nodes in a way that reverses order.
- Use existing canonical anchor relocation/block selection rather than creating another matcher.

Verification:
- Run the narrowest relevant existing viewer checks and document any known limitation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
