---
id: epic_028
title: Make epic close reviews visible in the War Room
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
created: '2026-10-30'
updated: '2026-11-03'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Make epic close reviews visible in the War Room

## Intent

When closing an epic requires an implementation review, the War Room should show a durable, clickable review action on that epic. The operator should be able to follow the review, return after a refresh, and see when closeout has finished without guessing what `pending_close_review` means or searching the forge.

`epic_026` exposed the gap. The close API returned `pending_close_review`, and PR #106 existed, but the UI supplied no usable link. The current close handler writes a review URL into status text when one is returned; `setStatus` uses `textContent`, so that URL is plain text and disappears on refresh. The board view attaches review state to Features but not to Epics.

Epic closure also currently requires two reviews: one to merge the epic implementation branch and another that effectively only moves the epic plan to completed. This epic collapses those steps. The implementation review must include the completed-state plan move, and reconciliation must finish closure from that same review after its merge is verified.

### Success criteria

- Represent the epic close stage explicitly: implementation review pending, completed, or an actionable blocker. Keep the review URL, source and target branches, and forge state with the stage. Reconstruct this state after a service restart; a transient button response is not the only source of truth.
- When `Close epic` opens or finds the implementation review, return its URL in the API response and render an `Open implementation review` link beside the epic's Close action. The link remains on the Epic row after board refresh, navigation, and restart.
- Generate the completed-state epic plan move on the epic implementation branch before opening its review. Do not open a second terminal closeout review after the implementation review merges.
- Keep the original close action pending while the implementation review is open. After it merges, reconcile the same action automatically, or expose a clear `Finish close` action if automatic reconciliation cannot run. Show completion only after the review merge and completed epic document on remote trunk are verified.
- Make `Close epic` idempotent while a review is pending: it reveals the existing review and never creates a second PR.

## Macro-architecture

Extend the existing epic close result, review lookup, board serialization, and War Room Epic row. Before the implementation review is opened, stage the epic document's move to completed in the same branch and commit as the implementation changes. Reuse the normal forge review snapshot and close action reconciliation path as the single authority for pending closure. After merge, verify both the merged review and the completed document on remote trunk, then finalize the close action without creating a terminal review.

The feature review row and backlog cancellation review link are useful UI precedents.

## Cross-module constraints

- Do not merge reviews automatically or change the human review policy.
- Do not modify the operator product-trunk checkout.
- Keep review URLs as validated external links and avoid rendering forge text as HTML.
- Preserve the existing safe external-link component and review registry rather than introducing a separate transient UI status store.
- The completed-state move and implementation changes must share one review; no terminal-only closeout PR may be created.

## Core dependencies

- Existing epic close API and close action reconciliation.
- Forge review lookup and durable review snapshot.
- Epic worktree document lifecycle and remote-trunk verification.
- War Room board serialization and Epic row rendering.

## Feature breakdown

The Epic Team will sequence a smallest shippable slice covering: single-review close preparation and reconciliation; durable pending-review state and API/board exposure; and War Room Epic-row controls. API and browser coverage should exercise the pending stage, failed review lookup, link accessibility, refresh, idempotency, merged-review reconciliation, and completion without a second PR.

## Acceptance scenarios

- Closing a ready epic stages the completed-state plan move with its implementation changes, opens one implementation review, and immediately shows a clickable link on the Epic row.
- Refreshing the page or restarting Cascade retains the review link and pending stage without another Close click.
- Repeated close requests while the review is open reveal the same review and do not create another PR.
- After the implementation review merges, automatic or operator-triggered reconciliation verifies both the merge and completed epic document on remote trunk, moves the epic to completed, and removes the pending review action.
- No terminal closeout review is opened at any point.
- A missing review URL or failed merge/document verification yields a specific actionable blocker rather than a bare `pending_close_review` label.
- API and browser tests cover pending review, missing or failed review lookup, link accessibility, refresh, idempotency, merged-review reconciliation, and completion. The dirty operator checkout stays unchanged throughout.

## Open questions

_(none)_

## Decision log

- 2026-10-30 · Human · Promoted the draft in `docs/briefs/epic_close_review_workflow.md` to the War Room backlog.
- 2026-11-03 · Human · Collapse epic closure into one review: the implementation PR also moves the epic plan to completed, and post-merge reconciliation verifies and finalizes closure without a terminal-only PR. In reply to: cmt_001.

## Amendment log

_(none)_
