# War Room latency benchmark baseline

## Reproduce

From the repository root, install the optional browser dependency once, then run:

```bash
python -m pip install playwright
playwright install chromium
python tests/war_room/benchmark_latency.py \
  --runs 20 \
  --output tests/war_room/baselines/task_023_003_001.json
```

The runner creates an isolated temporary Git workspace, starts the production
loopback War Room server on an ephemeral port, and opens a fresh 1440×1000
Chromium context for every sample. The fixed fixture contains 1 active and 2
backlog epics, 10 backlog features per epic, and 2 backlog tasks per feature
(93 cards total).
It never reads or mutates the developer's current board. Each page uses the
normal `cache: "no-store"` request and normal error reporting.

## Metric boundaries

- `navigation_to_usable_board_ms`: navigation start to a visible `epic_901`
  board row followed by two animation frames. A missing row or load error fails
  the run; it is not converted into a timing.
- `board_api_ms`: browser Resource Timing `requestStart` to `responseEnd` for
  the initial `GET /api/board`.
- `render_ms`: `renderBoard` entry to completion of its synchronous DOM update,
  recorded as the `cascade.board.render` Performance measure.
- `action_feedback_ms`: dispatch of a click on the fixed epic row through the
  selected-row DOM update and two animation frames. This is non-mutating UI
  feedback, so the benchmark cannot activate or dispatch lifecycle work.

Raw measurements and capture metadata live in
`tests/war_room/baselines/task_023_003_001.json`. Preserve that file and write a
new result alongside it for before/after comparison; do not compare runs made
with a different fixture, viewport, browser family, or host.

## Baseline finding

Across 20 samples, the initial board API dominates application work: its p95 is
approximately 85% of navigation-to-usable-board p95, while synchronous render
is under 10% and action feedback fits within roughly two frame intervals. The
next task should profile and reduce canonical board projection (`merged_board`,
sidecar/review/readiness projection, and priority loading) before considering
DOM micro-optimizations. The result does not justify weakening the fresh board
read or hiding projection errors.
