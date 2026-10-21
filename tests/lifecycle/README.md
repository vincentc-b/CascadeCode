# Lifecycle sandbox scenario (feat_004)

Repeatable, disposable pytest coverage for approval → dependency gating → dispatch → task merge → open review → feature rollup → restart reconciliation → epic rollup. Implemented in tasks **task_009** (fixtures) and **task_010** (end-to-end scenario).

## Prerequisites

- **Python 3.12+** (see `requires-python` in `pyproject.toml`)
- **Git** on `PATH` (scenario seeds a real repo and merges task branches)
- **Editable install with dev deps** from the repository root:

  ```bash
  pip install -e ".[dev]"
  ```

No Playwright or browser driver is required for the current scenario. The War Room HTTP server runs in-process on a free loopback port.

## Run the scenario

From the repository root, on a clean machine or CI job (no prior Cascade state needed):

```bash
pytest tests/lifecycle/ -v
```

To run only the full approval-to-rollup path:

```bash
pytest tests/lifecycle/test_approval_to_rollup_scenario.py::test_lifecycle_approval_to_rollup_system_scenario -v
```

Pytest uses disposable directories under `tmp_path`; fixtures tear down automation memory, hooks, and task runs after each test.

## What gets seeded

`seed_lifecycle_scenario()` (see `scenario.py`) builds a minimal board:

| Id | Role |
|----|------|
| `epic_090` | Parent epic |
| `feat_090` | Gate feature (no dependency) |
| `feat_091` | Follow feature (`depends_on: feat_090`) |
| `task_090` / `task_091` | Tasks under each feature |

Public entry points used: `activate_epic`, `approve_feature`, `reconcile_approval_dispatch`, `merge_task_branch`, `reconcile_completion_with_prompts`, `advance_work`, and War Room `GET /api/board`.

Agent boot and real forge I/O are **not** invoked: `quiet_lifecycle_dispatch` stubs dispatch, and review MRs are recorded in `.cascade/reviews.json` via test helpers.

## Lifecycle checkpoints

The system scenario test (`test_lifecycle_approval_to_rollup_system_scenario`) asserts behavior at these boundaries:

1. **Approval** — Both features are approved; gate feature is **active**, follow stays in backlog.
2. **Dependency gating** — Follow feature has **no** `FeatureReadyToPlan` / `TaskDispatched` events; manual dispatch of blocked follow is refused.
3. **Dispatch (gate)** — Gate task was dispatched exactly once; an active task run exists.
4. **War Room board** — `/api/board` lists gate under active features and follow under backlog.
5. **Task merge (gate)** — Merging `task_090` completes the gate feature on disk; **open feature review** blocks epic feature rollup until the MR is closed.
6. **Review close + rollup (gate)** — Closing the recorded review rolls gate completion into the epic (`FeatureCompleted` on the epic stream).
7. **Dispatch (follow)** — `reconcile_approval_dispatch` releases follow feature and task **once**; repeated reconcile after `reset_automation_memory()` does not duplicate dispatch.
8. **Task merge + review (follow)** — Same merge-then-review ordering; rollup blocked until review closes.
9. **Epic rollup** — After follow review closes, both features count toward the epic and an `epic_ready_to_close` toast is emitted once.
10. **Restart reconciliation** — After `reset_automation_memory()`, `advance_work` and `reconcile_completion_with_prompts` are **idempotent** (no extra dispatch or rollup).

Setup-only tests in `test_scenario_setup.py` cover seed/teardown safety, blocked dispatch, dependency release, War Room reads, and review-registry idempotence.

## Cleanup and troubleshooting

| Symptom | Likely cause | What to do |
|--------|----------------|------------|
| `git` / `commit` failures during merge steps | Git not installed or misconfigured | Ensure `git` works; scenario uses default local identity in temp repos only |
| Port bind errors for War Room | Rare loopback exhaustion | Re-run; fixture picks a free port per test |
| Stale automation between local runs | Prior dev session left global state | Tests call `teardown_lifecycle_scenario`; restart pytest process if you patched globals outside fixtures |
| Import errors for `cascade` | Package not installed | `pip install -e ".[dev]"` from repo root |

Fixtures always call `teardown_lifecycle_scenario()` after each test; no manual cleanup is required for CI or local pytest runs.

## Known limitations (by design)

- **No live agent or Cursor boot** — dispatch is stubbed so CI stays deterministic and fast.
- **No real GitHub/GitLab forge** — merge requests are simulated in `.cascade/reviews.json`.
- **No Playwright UI walkthrough** — board state is checked via HTTP API and store/events; browser harness can reuse the same fixtures later.
- **Single scripted path** — one gate/follow dependency chain, not an exhaustive lifecycle matrix.

## Related code

- `scenario.py` — seed, helpers, War Room fixture
- `conftest.py` — `lifecycle_scenario`, `lifecycle_war_room` pytest fixtures
- `test_approval_to_rollup_scenario.py` — full system scenario (task_010)
- `test_scenario_setup.py` — disposable setup checks (task_009)
