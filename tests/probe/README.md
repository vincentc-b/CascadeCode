# Disposable lifecycle readiness probe (feat_012_003)

Operator- and developer-invoked synthetic Epic → Feature → Task exercise in a **disposable** git workspace. The probe validates readiness transitions, watchdog/reconciliation activity, convergence detection, and intentional stall recovery. It never reads from or writes to the live Cascade board in your product checkout.

## Prerequisites

- **Python 3.12+** and **Git** on `PATH`
- Editable install from the repository root: `pip install -e ".[dev]"`

## Invocation

Full lifecycle probe (success path plus intentional stall and recovery):

```bash
python -m cascade.cli probe run --json
```

Allocate and verify a disposable workspace only (no lifecycle exercise):

```bash
python -m cascade.cli probe prepare --json
```

Optional flags:

| Flag | Meaning |
|------|---------|
| `--parent PATH` | Directory that will contain the new `run-<uuid>` workspace (default: `$TMPDIR/cascade-probe`) |
| `--json` | Single JSON object on stdout (recommended for scripts) |
| `--debug-retain` | **Debug only:** leave the workspace directory on disk after success |

Bounded runtime is controlled by `CASCADE_PROBE_MAX_SECONDS` (default **300**). Runs are safe to repeat; each invocation allocates a fresh workspace.

## Interpreting results

**`probe run`** exit code **0** means all phases passed; **1** means a phase failed or the run hit a probe error/timeout.

With `--json`, stdout includes:

- `ok` — overall pass/fail
- `failing_phase` — first failing phase name, or `null` on success
- `phases` — list of `{ "phase", "ok", "detail" }` rows in execution order
- `workspace` — absolute path to the disposable repo (see cleanup below)
- `retained` — whether `--debug-retain` kept artifacts

Phases exercised on a successful run include:

`synthetic_lifecycle`, `readiness_transitions`, `watchdog_reconciliation`, `convergence_detection`, `intentional_stall`, `stall_diagnostic`, `stall_recovery`, `stall_re_emit`.

Human-readable output (without `--json`) prints `probe lifecycle ok` or `failed` and the failing phase name.

## Cleanup and debug retention

By default, the workspace directory is **removed** when the command finishes, whether or not `--json` is set. The live board is never used as a mutation target; parent directories on live board paths are rejected.

With **`--debug-retain`**, the workspace remains on disk for inspection (`retained: true` in JSON). You must delete it manually when finished. Do not point `--parent` at production board paths.

## Rerun expectations

Each run creates a new git repository under the probe parent directory. Failures are idempotent: fix the underlying issue and rerun. Timeouts raise a bounded-execution error; increase `CASCADE_PROBE_MAX_SECONDS` if a slow environment needs more headroom.

## Automated coverage

From the repository root:

```bash
pytest tests/probe/ -v
```

End-to-end scenarios live in `test_lifecycle_scenarios.py` (CLI and in-process). Harness guardrails (live-board rejection, deadlines) are covered in `test_workspace_harness.py` without duplicating the full lifecycle path.
