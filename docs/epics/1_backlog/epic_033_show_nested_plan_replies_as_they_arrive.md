---
id: epic_033
title: Show nested plan replies as they arrive
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6.1-sol
  epic_architect: gpt-6.1-sol
  feature_lead: gpt-6.1-sol
  feature_architect: gpt-6.1-sol
  swe: gpt-6.1-sol
---
# Show nested plan replies as they arrive

## Intent

A human continuing a conversation in a plan review thread must see the agent's response in that same thread without refreshing or searching the War Room chat. In the epic_028 incident on 2026-11-03, human replies cmt_006 and cmt_008 were durably delivered and the agents answered with cmt_007, cmt_009, and cmt_010. The plan viewer rendered only cmt_001 and its direct children; `groupCommentThreads` drops grandchildren. It also calls `loadComments` only at page load and after a local post/resolve, so agent replies that arrive later remain invisible in an open page. A local reproduction using the stored parent links hides all three agent replies. This is a visibility defect, not evidence that the agents ignored the comments.

### Success criteria

1. Render every descendant of a root plan comment, including replies to replies, in deterministic chronological order with clear author and reply-to context. Keep the full chain visible for Epic and Feature plans in both inline and comment-tray placements. A reply whose parent is missing or malformed remains visible with a safe fallback instead of disappearing. Do not render any comment twice.
2. While the plan page is open, show newly stored agent and human replies promptly without a manual page refresh. Use a bounded, lifecycle-safe refresh or event stream; pause or reduce work when the page is hidden and recover after reconnect/reload. Preserve unsent reply drafts, scroll position, open controls, inline placement, and resolved/outdated styling during updates.
3. Keep posting behavior and durable queue delivery intact: a human reply to any visible thread creates one comment event and one owning-team kickoff, and the agent response appears under the intended parent. Repeated polling, reconnection, and refresh do not duplicate comments or turns.
4. Reproduce the epic_028 chain (cmt_001 → cmt_006 → cmt_007 and cmt_001 → cmt_008 → cmt_009/cmt_010) in browser tests. Prove all replies are visible after initial load and after an asynchronous agent reply arrives. Cover a missing parent, multiple nesting levels, Epic and Feature plans, and draft preservation.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use the existing comment sidecar, `/api/comments/{id}`, and current comment/event IDs as the source of truth. Do not rewrite historical comments or create a second conversation store. Keep agent replies attached to the comment they answered; do not flatten away parent identity in storage. Keep the UI accessible (keyboard and screen-reader context for reply depth/parent), avoid unbounded polling or a full plan rerender on every tick, and do not start agent turns merely because the browser refreshes comments. The fix should make agent replies visible, not imply that every human ping needs a new answer once the plan question has already been resolved.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
