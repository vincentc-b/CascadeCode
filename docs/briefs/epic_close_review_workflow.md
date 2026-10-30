# Draft brief: Make epic close reviews visible in the War Room

## Intent

When closing an epic requires an implementation or terminal closeout review, the War Room should show a durable, clickable review action on that epic. The operator should be able to follow the review, return after a refresh, and see when closeout has finished without guessing what `pending_close_review` means or searching the forge.

`epic_026` exposed the gap. The close API returned `pending_close_review`, and PR #106 existed, but the UI supplied no usable link. The current close handler writes a review URL into status text when one is returned; `setStatus` uses `textContent`, so that URL is plain text and disappears on refresh. The board view attaches review state to Features but not to Epics. One terminal-review verification path also returns `pending_close_review` without a `review_url`.

## Required behavior

1. Represent the epic close stage explicitly: implementation review pending, terminal closeout review pending, completed, or an actionable blocker. Keep the review URL, source and target branches, and forge state with the stage. Reconstruct this state after a service restart; a transient button response is not the only source of truth.
2. When `Close epic` opens or finds a review, return its URL in the API response and render an `Open implementation review` or `Open closeout review` link beside the epic's Close action. The link must remain on the Epic row after board refresh, navigation, and restart. Reuse the existing safe external-link component.
3. Resolve an existing terminal review URL even when the remote epic document is already completed but merge verification has not yet succeeded. A pending state without a URL must give a specific lookup or verification error, not a bare `pending_close_review` label.
4. Keep the original close action pending while either review is open. After the relevant merge lands, reconcile the same action automatically, or expose a clear `Finish close` action if automatic reconciliation cannot run. Show completion only after the terminal review and remote trunk revision are verified.
5. Make `Close epic` idempotent while a review is pending: it should reveal the existing review and never create a second PR. Do not merge reviews automatically or change the human review policy. Do not modify the operator product-trunk checkout.

## Acceptance scenarios

- Closing a ready epic opens its implementation review and immediately shows a clickable link on the Epic row.
- After that review merges, closing or reconciling opens one terminal closeout review and replaces the row link with the terminal review link.
- Refreshing the page or restarting Cascade retains the correct link and stage without another Close click.
- A pending terminal review whose remote document already says completed still shows its review link until the merge is verified.
- Once the terminal review lands, the epic moves to completed and the pending review action disappears. Repeated close requests remain safe.
- API and browser tests cover the two pending stages, missing or failed review lookup, link accessibility, refresh, and completion. The dirty operator checkout stays unchanged throughout.

## Implementation boundaries

Extend the existing epic close result, review lookup, board serialization, and War Room Epic row. Reuse the normal forge review snapshot and close action reconciliation path. The feature review row and backlog cancellation review link are useful UI precedents. Keep review URLs as validated external links and avoid rendering forge text as HTML.
