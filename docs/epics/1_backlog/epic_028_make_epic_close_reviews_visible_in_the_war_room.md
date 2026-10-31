---
id: epic_028
title: Make epic close reviews visible in the War Room
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
created: '2026-10-30'
updated: '2026-10-30'
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Make epic close reviews visible in the War Room

## Intent

When closing an epic requires an implementation or terminal closeout review, the War Room should show a durable, clickable review action on that epic. The operator should be able to follow the review, return after a refresh, and see when closeout has finished without guessing what `pending_close_review` means or searching the forge.

`epic_026` exposed the gap. The close API returned `pending_close_review`, and PR #106 existed, but the UI supplied no usable link. The current close handler writes a review URL into status text when one is returned; `setStatus` uses `textContent`, so that URL is plain text and disappears on refresh. The board view attaches review state to Features but not to Epics. One terminal-review verification path also returns `pending_close_review` without a `review_url`.

### Success criteria

- Represent the epic close stage explicitly: implementation review pending, terminal closeout review pending, completed, or an actionable blocker. Keep the review URL, source and target branches, and forge state with the stage. Reconstruct this state after a service restart; a transient button response is not the only source of truth.
- When `Close epic` opens or finds a review, return its URL in the API response and render an `Open implementation review` or `Open closeout review` link beside the epic's Close action. The link remains on the Epic row after board refresh, navigation, and restart.
- Resolve an existing terminal review URL even when the remote epic document is already completed but merge verification has not yet succeeded. A pending state without a URL gives a specific lookup or verification error, not a bare `pending_close_review` label.
- Keep the original close action pending while either review is open. After the relevant merge lands, reconcile the same action automatically, or expose a clear `Finish close` action if automatic reconciliation cannot run. Show completion only after the terminal review and remote trunk revision are verified.
- Make `Close epic` idempotent while a review is pending: it reveals the existing review and never creates a second PR.

## Macro-architecture

Extend the existing epic close result, review lookup, board serialization, and War Room Epic row. Reuse the normal forge review snapshot and close action reconciliation path. The feature review row and backlog cancellation review link are useful UI precedents.

## Cross-module constraints

- Do not merge reviews automatically or change the human review policy.
- Do not modify the operator product-trunk checkout.
- Keep review URLs as validated external links and avoid rendering forge text as HTML.
- Preserve the existing safe external-link component and review registry rather than introducing a separate transient UI status store.

## Core dependencies

- Existing epic close API and close action reconciliation.
- Forge review lookup and durable review snapshot.
- War Room board serialization and Epic row rendering.

## Feature breakdown

The Epic Team will sequence durable close-stage and review lookup state, API and board exposure, and War Room row controls. API and browser coverage should exercise the two pending stages, failed review lookup, link accessibility, refresh, and completion.

## Acceptance scenarios

- Closing a ready epic opens its implementation review and immediately shows a clickable link on the Epic row.
- After that review merges, closing or reconciling opens one terminal closeout review and replaces the row link with the terminal review link.
- Refreshing the page or restarting Cascade retains the correct link and stage without another Close click.
- A pending terminal review whose remote document already says completed still shows its review link until the merge is verified.
- Once the terminal review lands, the epic moves to completed and the pending review action disappears. Repeated close requests remain safe.
- API and browser tests cover the two pending stages, missing or failed review lookup, link accessibility, refresh, and completion. The dirty operator checkout stays unchanged throughout.

## Open questions

- Which existing review snapshot should be authoritative when the implementation and terminal reviews overlap during reconciliation?

## Decision log

- 2026-10-30 · Human · Promoted the draft in `docs/briefs/epic_close_review_workflow.md` to the War Room backlog.

## Amendment log

_(none)_
