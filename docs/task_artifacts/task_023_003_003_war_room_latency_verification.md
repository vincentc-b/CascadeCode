# War Room latency verification

## Result

The post-change War Room meets the feature gate: navigation to a usable board
has a **1,384.7 ms p95 across 20 runs**, below the 2,000 ms target. Raw samples
and capture metadata are retained in
`tests/war_room/baselines/task_023_003_003.json`; the unchanged comparison data
remain in `tests/war_room/baselines/task_023_003_001.json`.

The run used the same generated 3-Epic, 30-feature, 60-task fixture, 1440×1000
viewport, headless Chromium browser family, fresh browser context per sample,
and all four task-001 metric boundaries. The action check in the runner was
corrected before capture to inspect the newly rendered row after a click rather
than the detached pre-render node. This changes no timing boundary: the metric
still starts at click dispatch and ends after selected-row feedback plus two
animation frames.

## Environment

| | Before (task 001) | After (task 003) |
| --- | --- | --- |
| Samples | 20 | 20 |
| Platform | Linux 6.8 x86_64, glibc 2.39 | Linux 6.8 AWS x86_64, glibc 2.35 |
| Python | 3.12.12 | 3.12.8 |
| Browser | Chromium 141 headless | Chromium 156.0.8078.4 headless |
| Viewport | 1440×1000 | 1440×1000 |
| Before revision | `26532dc0c3c4bd0a8a14380110d75a8006b9ff99` | — |
| Captured revision | — | `63d41fe784e83966a5ff80aad6f287b9c8a8064f` plus the documented runner fix |

Both captures are the required Linux x86_64/headless-Chromium machine class,
but they are not the same physical host or browser build. Absolute deltas
therefore include host and browser variance and must not be read as isolated
optimization attribution. Task 002's controlled same-host server projection
measurement remains the attribution evidence: board projection p95 decreased
from 114.238 ms to 73.583 ms (35.6%).

## Same-fixture before/after timings

| Metric | Before p95 | After p95 | p95 delta | After median | After range |
| --- | ---: | ---: | ---: | ---: | ---: |
| Navigation to usable board | 182.7 ms | **1,384.7 ms** | +1,202.0 ms | 898.65 ms | 651.9–1,479.9 ms |
| Initial board API | 151.4 ms | 472.2 ms | +320.8 ms | 343.85 ms | 211.1–487.0 ms |
| Synchronous render | 8.3 ms | 19.0 ms | +10.7 ms | 11.65 ms | 4.7–19.5 ms |
| Action feedback | 32.4 ms | 42.1 ms | +9.7 ms | 36.15 ms | 29.6–43.2 ms |

All 20 runs produced usable-board, API, render, and selected-row feedback
measurements. Action feedback remained successful and below 50 ms in every
sample. Its 9.7 ms p95 increase is reported rather than hidden; it is less than
one 60 Hz frame, and no action-feedback product code changed in task 002.

## Freshness and error behavior

The verification suite exercises the retained behavior rather than relying on
the timing result alone:

- the initial and polled board path still uses a cache-busting `GET /api/board`
  request, coalesces concurrent refreshes, retries after a pending poll, and
  keeps visible error handling;
- merged-board invalidation still forces a new canonical snapshot while repeat
  readers reuse only the completed snapshot;
- the board endpoint still begins with one fresh merged-board scan and retains
  pending-review blockers;
- static responses remain `Cache-Control: no-store`, unknown routes/methods
  retain their JSON errors, and handler saturation retains its visible 503
  `server busy` response.

These checks are covered by the focused supervised test command recorded with
the task delivery.
