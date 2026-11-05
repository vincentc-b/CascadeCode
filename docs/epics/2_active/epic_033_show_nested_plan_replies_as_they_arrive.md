---
id: epic_033
title: Show nested plan replies as they arrive
tier: epic
status: active
parent: null
children:
- feat_033_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-03'
updated: '2026-11-05'
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

One feature owns the complete visibility fix: normalize the existing comment response into complete threads, render those threads consistently in inline and tray placements, and refresh comment state while the plan is open. Preserve stored immediate-parent links and existing comment IDs; chronological presentation may flatten visual depth while retaining accessible reply-to context.

Use deterministic oldest-first ordering within each thread with comment ID as a tie-breaker. Missing-parent, self-parent and cyclic relationships must terminate safely and show every valid comment exactly once. Keep fallback comments visible in the tray when an inline anchor is unavailable.

Prefer a small lifecycle-owned polling loop over introducing streaming infrastructure: target new-reply visibility within 5 seconds of successful API availability while visible and connected. Allow one in-flight request, pause periodic requests while hidden, refresh on visibility/reconnect, retain last successful data on failure and use capped retry backoff. Ignore stale responses after navigation or unmount. The feature team may choose an existing event stream if it already satisfies these constraints.

Merge comment data by stable identity without remounting the plan or replacing local draft/control state. Refresh is read-only; posting and owning-team dispatch remain on their existing path.

## Cross-module constraints

Use the existing comment sidecar, `/api/comments/{id}`, and current comment/event IDs as the source of truth. Do not rewrite historical comments or create a second conversation store. Keep agent replies attached to the comment they answered; do not flatten away parent identity in storage. Keep the UI accessible (keyboard and screen-reader context for reply depth/parent), avoid unbounded polling or a full plan rerender on every tick, and do not start agent turns merely because the browser refreshes comments. The fix should make agent replies visible, not imply that every human ping needs a new answer once the plan question has already been resolved.

## Core dependencies

- Existing comment sidecar and `/api/comments/{id}` response, including stable IDs, timestamps and immediate-parent links.
- Shared `groupCommentThreads`, plan comment renderer, inline anchors and comment tray used by Epic and Feature plans.
- Plan-page lifecycle and comment state ownership; existing posting/event/queue integration.
- Existing browser harness and posting/dispatch regression coverage.

The implementation repository is not available in this planning workspace. Before coding, the feature team must verify API response completeness, shared renderer boundaries, stable identity fields and local state ownership. Any required storage/API contract change comes back to epic review; no separate spike or backend redesign is authorized by this plan.

## Feature breakdown

1. **feat_033_001 — Render complete plan threads and refresh incoming replies.** Delivers all four success criteria as one shippable slice. No feature dependency. Sequence within the feature: inspect existing contracts, fix complete-thread rendering, add lifecycle-safe refresh, then validate the integrated behavior.

Use browser coverage for the epic_028 initial-load and delayed-reply reproduction across Epic/Feature and inline/tray placements. Include draft/focus/control/scroll preservation, missing parents and deeper chains. Add narrow grouping checks for cycles and equal timestamps where cheaper than browser coverage. Reuse existing posting/queue tests to prove one human submission creates one event and one owning-team kickoff, and refresh/reconnect creates no writes or turns. Do not add redundant coverage or a new test framework.

## Open questions

No product-scope questions remain. Implementation readiness checks belong to feat_033_001: confirm the API returns all descendants, state updates preserve local UI state, malformed links cannot hide comments, and refresh cannot dispatch turns. Escalate a failed contract assumption before expanding scope.

Out of scope: historical comment rewrites, a second conversation store, queue redesign, new notification infrastructure, and changing whether a resolved human ping warrants another agent answer.

## Decision log

- 2026-11-03 · Human · Brief approved through merge request review.

- `dec_001` · 2026-11-05 · Epic Manager · **Scope and delivery**
  Chose Deliver all four visibility success criteria in feat_033_001 as one vertical slice; exclude storage migration, queue redesign and notification infrastructure..
  Rationale: Rendering and refresh must work together to solve the reported conversation visibility defect. One feature avoids coordination overhead and preserves the existing durable delivery contract.
  Honors: Original Intent; Success criteria 1–4; Cross-module constraints; frugal-engineering and product-manager guidance.

- `dec_002` · 2026-11-05 · Epic Manager · **Observable behavior and validation**
  Chose Use deterministic oldest-first thread ordering with ID ties, safe malformed-parent fallback, and a visible-page refresh target of 5 seconds after successful API availability; prefer lifecycle-owned polling and a compact browser regression matrix..
  Rationale: Makes prompt visibility and complete threading testable without new infrastructure. Read-only refresh, bounded retries, stable UI state and existing dispatch regression checks contain the main implementation risks.
  Honors: Success criteria 1–4; accessibility and lifecycle constraints; economical testing.
## Amendment log

_(none)_
