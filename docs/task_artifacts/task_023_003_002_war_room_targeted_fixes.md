# War Room targeted latency fixes

## Evidence mapping

The task 001 baseline identified canonical `GET /api/board` projection as the
dominant application cost (151.4 ms p95, about 85% of usable-board p95). A
profile of that same 93-card fixture identified two repeated operations inside
the projection:

- active-Epic plan readiness rescanned the board twice while deriving and then
  validating the same canonical plan revision;
- each of 30 backlog features independently resolved and loaded its own and its
  shared Epic comment sidecars for the review-thread readiness gate.

The retained changes reuse the already-selected canonical Epic metadata and
batch the comment gate projection. The command and lifecycle boundaries keep
their existing single-item evaluators, and `/api/board` still begins with the
same `merged_board` read and propagates the same board, priority, and I/O errors.

## Focused before/after measurement

Both samples used revision `a267484`'s fixed fixture, 20 fresh merged-board
projections, and the task 001 metric environment (Linux x86_64, Python 3.12).
The measured boundary was the server-side work behind `GET /api/board`:
`merged_board` through board serialization and priority projection. The
pre-change sample ran from an archive of `a267484`; the post-change sample ran
from this worktree.

| Projection timing | Before | After | Change |
| --- | ---: | ---: | ---: |
| median | 91.392 ms | 63.418 ms | -30.6% |
| p95 | 114.238 ms | 73.583 ms | -35.6% |

Pre-change raw milliseconds:

```text
91.717, 114.238, 91.489, 91.295, 90.553, 90.565, 93.009, 92.624,
91.593, 90.525, 90.407, 89.663, 115.198, 90.146, 90.695, 90.617,
92.583, 92.087, 91.706, 91.211
```

Post-change raw milliseconds:

```text
62.554, 60.238, 59.515, 61.265, 64.382, 63.715, 64.614, 63.975,
67.436, 63.013, 62.488, 62.585, 63.357, 73.583, 79.661, 62.416,
62.728, 63.479, 64.069, 63.758
```

The browser benchmark could not bind its loopback socket in the managed task
sandbox (`PermissionError: operation not permitted`). No browser, DOM, polling,
or action-feedback code changed; task 003 remains responsible for the required
same-browser 20-run final comparison across all four metrics.
