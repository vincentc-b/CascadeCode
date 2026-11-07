# task_038_001_001 — Dependency compatibility contract

This decision record pins the behavior that authoritative dependency status must
preserve. The dependency projection is read-only evidence, not action authorization.

## Authoritative board and snapshot semantics

- Planning documents are owned by the configured tracking repository. Calls made
  from the target checkout or one of its managed worktrees route planning reads and
  writes to that tracking root; dependency evaluation must use the same canonical
  tracking trunk.
- Lifecycle completion requires both `status: completed` and placement in
  `3_completed`. A completed, non-pointer epic on the tracking trunk takes precedence
  over stale active copies retained in registered worktrees.
- The merged board combines the tracking trunk with registered integration
  worktrees. Its short-lived process cache is invalidated by board, registry, and
  backlog-snapshot publication writes. A request-scoped `merged_board_snapshot`
  deliberately keeps one fixed board view for the duration of a read-only response;
  after the scope exits, the next read observes invalidation. Neither the cache object
  nor a scoped snapshot is an authorization token for a later mutation.

## Explicit action gates

- Dependency completion alone does not authorize dispatch. Feature dispatch still
  applies approval, parent, cancellation, blocking-thread, sibling/review, stacked
  topology, and base-selection checks.
- With stacked reviews disabled, a completed predecessor whose review remains open
  blocks the successor. With stacking enabled, only the supported single-predecessor
  shape with durable predecessor review identity may use that predecessor branch.
- Review state remains an explicit action gate. A task depending on a completed
  feature remains undispatchable while that feature review is pending.
- Review publication retains its own rollup, source-worktree, and review-target
  checks; a dependency outcome must not bypass them.
