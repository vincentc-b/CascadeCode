---
id: epic_019
title: Comments should post inline
tier: epic
status: active
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Comments should post inline

## Intent

When a reviewer posts a line-anchored comment on an epic or feature plan, keep the resulting thread beside the plan content where the comment was started instead of moving it to the bottom review tray. This preserves reading context without changing comment persistence or workflow semantics.

### Success criteria

- After a line-anchored comment is posted, its thread renders immediately after the resolved plan block that contains the anchor.
- Existing line-anchored threads render at that same inline location when the page loads or comments refresh.
- Replies, resolve controls, blocking state, resolved state, and outdated-anchor indication continue to work in the inline thread.
- Multiple threads anchored to one rendered block have deterministic ordering and do not displace or duplicate one another during refresh.
- Whole-plan comments and threads whose anchor cannot be placed remain available in the bottom review tray.
- Epic and feature plan pages support the behavior; task pages remain unchanged.
- The behavior remains usable on narrow viewports and by keyboard, with status updates still exposed to assistive technology.

## Macro-architecture

Implement placement in the War Room plan-viewer client. Reuse the existing comment API, sidecar schema, source-line metadata, anchor relocation logic, and thread controls. Split rendered root threads into two destinations:

1. Placeable line-anchored threads are inserted adjacent to their resolved `[data-src-line]` plan block.
2. Global or unplaceable threads are rendered in the existing review tray.

The same thread node builder and refresh path must serve both destinations so posting, replying, resolving, polling, and state styling stay consistent. Styling should adapt the existing thread presentation for inline placement rather than introduce a parallel interaction model.

## Cross-module constraints

- Do not change comment storage records, API payloads, blocking gates, agent delivery, or resolution authorization.
- Treat persisted document SHA, line range, anchor text, and existing relocation helpers as the placement source of truth.
- Preserve a visible fallback for missing, invalid, or outdated anchors; no comment may disappear because inline placement fails.
- Preserve draft reply text and avoid duplicate thread nodes across polling or rerendering.
- Keep DOM order stable: source-block order first, then the API's existing thread order for threads sharing a block.
- Avoid broad Markdown-renderer changes; limit source mapping changes to defects required to place threads correctly.

## Core dependencies

- War Room plan page template and CSS.
- Plan viewer JavaScript comment grouping, placement, refresh, reply, and resolve behavior.
- Existing `GET /api/comments/{doc_id}`, `POST /api/comment`, and `POST /api/comment/resolve` contracts.
- Existing comment sidecar line-anchor fields and document SHA.

## Feature breakdown

1. **Render anchored review threads inline** — Update the plan viewer to route placeable root threads beside their anchored content, retain the bottom tray for global/unplaceable threads, preserve all thread interactions across refresh, and add focused UI regression coverage.

## Open questions

- None blocking. The fallback tray is the explicit product behavior when an anchor cannot be placed safely.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-10-22 · Epic Manager · Scope is limited to client-side placement and presentation; comment persistence, APIs, gates, and agent workflows remain unchanged.
- 2026-10-22 · Epic Manager · Global and unplaceable threads remain in the existing bottom review tray so inline placement never hides a comment.
- 2026-10-22 · Epic Manager · Deliver as one end-to-end feature because the behavior is localized to one viewer flow and splitting it would add coordination without independent user value.

## Amendment log

_(none)_
