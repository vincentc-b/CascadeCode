# Scoped architecture authoring and closeout

Cascade gives each Epic, Feature, and Task a revision-pinned architecture view. The view contains that work item's owned design/model artifacts and read-only pinned ancestor artifacts; it does not grant access to sibling plans or arbitrary repository files.

## Team workflow

1. Read the pinned planning context before proposing a design change.
2. Stage changes to artifacts owned by the current work item through the normal architecture review path. Changes to an ancestor or shared artifact become an amendment addressed to its owner; they do not modify the accepted baseline.
3. The addressed owner reads `read_architecture_amendments` with no caller-supplied owner ID, reviews the exact proposal, and stages it under its own authority when appropriate.
4. At Task, Feature, and Epic completion, record a reconciliation receipt for the exact landed implementation revision. The receipt either cites an accepted design/model update or gives a short no-change justification covering design and C4 impact.
5. Retry closure only after correcting a stale receipt or material mismatch. A split-repository promotion in `acceptance_pending` continues to block closure until both repository sides accept.

Historical reconstruction uses `read_historical_evidence` with an explicit scope. Only completed, non-cancelled work in the caller's owner lineage is eligible. Git evidence is limited to receipt-bound target commits still reachable from target `HEAD`; linked review evidence is keyed to the same work ID. Missing receipts, unreachable commits, unavailable review descriptions, and unavailable source revisions are returned as explicit `unavailable` reasons. The reader never substitutes current repository content or an unrelated review.

## Architecture notes

The implementation reuses four durable stores: revision-pinned work documents and architecture review units for planning context, `architecture/owner-amendments.json` for routed owner requests, `architecture/reconciliation-receipts.json` for implementation commit provenance, and the exact work-keyed `.cascade/reviews.json` row for authorized forge links. External amendment adapters derive the owner from the authenticated Epic, Feature, or Task tool context; an API caller cannot provide a different owner ID.

Accepted low-impact limitations:

- Legacy completed work without a reconciliation receipt returns `reconciliation_receipt_missing`; Cascade does not invent commit provenance.
- A forge description or source revision is returned from the authorized durable review row, its locally resolvable source branch, or the exact linked review through configured forge access. Otherwise the linked review remains visible with an explicit unavailable reason. Source revisions are not required to be ancestors of target `HEAD`, because squash merges legitimately preserve a distinct reviewed source commit.
- Replay is one related work record per call. This keeps the existing tool boundary finite; callers page their own bounded lineage selection rather than requesting arbitrary repository ranges.
