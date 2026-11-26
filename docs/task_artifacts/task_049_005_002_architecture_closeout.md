# Bounded transcript contention architecture closeout

This record reconciles the implementation at
`afc7579a00a3993f2923e3d5bb4c88bb9f819f73`. The final supervised validation
is recorded by the Task lifecycle against the evidence-only descendant commit.
No accepted architecture snapshot or review lineage is changed.

## Diagram impact inventory

| View | Owning design | Integrated source and disposition | Verification |
|---|---|---|---|
| `cascade-landscape`, `cascade-context` | Root `DESIGN.md` | No actor, external system or responsibility boundary changed. The diff bounds work inside the existing Service and War Room runtimes. | Source-contract validation and the pinned browser entry at context passed; no design edit was needed. |
| `cascade-containers` | Root `DESIGN.md` and `cascade/DESIGN.md` | No runtime or persistence boundary changed. Recovery publisher SQLite, transcript JSONL/index and lock files remain stores used by existing Python containers, not new OS-isolated services. | The native render and context-to-container browser transition passed; both designs already describe the owning runtime and stores. |
| `cascade-supervisor-components` | `cascade/watchdog/DESIGN.md` and `cascade/recovery_progress/DESIGN.md` | `publish_committed_transition`, `drain_recovery_progress`, `record_transcript_milestone`, `_record_transcript_milestone`, `_publisher_lock` and `_connect` share caller deadlines and preserve pending replay. `_connect` refreshes the remaining busy timeout before every schema statement. Component topology is unchanged. | Normal, contention, sequential-timeout and replay tests passed; browser navigation reached Watchdog from the supervisor component. |
| `cascade-war-room-components` | `cascade/war_room/DESIGN.md` | `append_committed_recovery_receipt`, `graph_transcript_fence`, `fenced_transcript_source_acknowledgement`, `_connect_index` and `_connect_existing_index` keep append and current routing inside Dashboard. Both connection paths refresh the remaining timeout before each sequential statement; the existing-index lookup does not initialize, import, repair or publish. | Store, remaining-budget and milestone tests passed; browser navigation reached Dashboard from the War Room component. |
| `cascade-watchdog-code` | `cascade/recovery_progress/DESIGN.md` and `cascade/watchdog/DESIGN.md` | Existing publisher fast-path, drain, public writer and mapping nodes retain their semantic IDs and real Function declarations. Descriptions now state the shared deadline and filesystem/source baseline. | Source-path/symbol/kind validation, real render, Explore, Level up and pinned `publish_committed_transition` source passed. |
| `cascade-dashboard-code` | `cascade/war_room/DESIGN.md` | Added Function node `element.code.dashboard.chat.existing-index` for `_connect_existing_index`; rerouted fenced lookup from the schema-opening writer connection to that node; added recovery append to current fenced acknowledgement. Model, view and contract declarations changed together. | Source-path/symbol/kind validation, real render, Explore, Level up, restored deep link and pinned `_connect_existing_index` source passed. |
| `cascade-workspace-code` | `cascade/workspace/DESIGN.md` | Owner resolution behavior and its source declarations did not change. Only implementation-design discovery changed: `cascade/recovery_progress` now resolves to its own artifact and `DESIGN.md`, so no Workspace Code node or edge changed. | The mapping ownership assertion and pinned design-resource discovery passed. |
| Supplementary behavior | `cascade/recovery_progress/DESIGN.md` and `cascade/war_room/DESIGN.md` | The current sequence covers publisher-before-graph acquisition, mapping commit before fence release, deadline exhaustion to pending, and restart/drain replay. SQLite mapping/index state and authoritative transcript state remain distinct. | Traced against the named contention/replay fixtures below and the source entry points above. |

Reviewed `DESIGN.md`, `cascade/DESIGN.md`,
`cascade/recovery_progress/DESIGN.md`, `cascade/war_room/DESIGN.md`,
`cascade/watchdog/DESIGN.md` and `cascade/workspace/DESIGN.md` against the final
implementation diff. Requirement and decision ownership remains in the child
designs; parent documents only link or summarize their interfaces. The changed
design prose contains current rules and rationale, not delivery chronology.
`REQ-RECOVERY-PROGRESS-004` now distinguishes measured lock/SQLite contention
from uninterruptible admitted filesystem opens, source reads, JSONL append and
fsync.

## Validation evidence

The focused integrated command was:

```text
/opt/conda/bin/python3.12 -m pytest -q \
  tests/recovery_progress/test_publisher.py \
  tests/recovery_progress/test_transcript_milestones.py \
  tests/war_room/test_durable_chat_store.py \
  tests/war_room/test_recovery_progress_api.py \
  tests/war_room/test_transcript_pages_api.py \
  tests/architecture/test_reconstructed_design.py \
  tests/workspace/test_c4_source.py
```

That command did not pass: it produced 90 passes and two historical-reconstruction
failures. Those assertions require the original `task_034_007_002` contract owner
and baseline hash while the current pinned contract is owned by `epic_049`; they
were not relaxed or counted as green. The scoped current checks passed with:

```text
/opt/conda/bin/python3.12 -m pytest -q \
  tests/architecture/test_reconstructed_design.py::test_every_python_directory_has_exact_design_ownership \
  tests/workspace/test_c4_source.py \
  tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache
```

Result: 16 passed in 69.83 s. This validates exact design ownership, all current
source symbols and declaration kinds, supported local rendering, native Code
coverage and a same-artifact cache hit. `git diff --check` also passed.

The six deterministic contention cases passed in 2.56 s. Their measured pytest
call durations were:

- publisher drain thread lock: 0.36 s;
- publisher drain SQLite writer lock: 0.29 s;
- graph thread contention with drain replay: 0.42 s;
- 250 ms fast-path graph thread contention: 0.45 s;
- second-process graph `flock`: 0.35 s;
- append SQLite writer contention and replay: 0.36 s.

The drain/thread/SQLite/process-fence cases assert a 0.12–0.75 s elapsed window;
the 250 ms fast-path case asserts 0.15–0.8 s. Each contention fixture preserves
pending work and proves later completion; the mapping/store cases also reject
fabricated or duplicate state.

A local Chromium run used the real revision-pinned model and renderer. It
traversed context → containers → supervisor components → Watchdog Code and
context → containers → War Room components → Dashboard Code. It opened pinned
source for `publish_committed_transition` and `_connect_existing_index`, used
Level up from both Code views, reloaded the Dashboard deep link with the index
node selected, and reused snapshot
`architecture-snapshot-a040e85e44f1c0616de822db98008fb05308c1ef1aa06acba4cb8726b6b728c6`.
Observed readiness was 16.079 s initially and 8.651 s after deep-link reload.
These are local measurements, not latency guarantees. The renderer's configured
process/time bounds were unchanged, and the render test verified warm artifact
reuse rather than per-view renderer startup.

The repaired integrated command at implementation revision
`afc7579a00a3993f2923e3d5bb4c88bb9f819f73` covered publisher, milestones,
durable store, recovery/transcript APIs, the held-executor transition boundary,
current source contracts and the real pinned render/cache fixture. Result:
92 passed in 135.19 s.

```text
python -m pytest -q \
  tests/recovery_progress/test_publisher.py \
  tests/recovery_progress/test_transcript_milestones.py \
  tests/war_room/test_durable_chat_store.py \
  tests/war_room/test_recovery_progress_api.py \
  tests/war_room/test_transcript_pages_api.py \
  tests/task/test_transition_receipts.py::test_execution_start_is_committed_before_held_executor_finishes \
  tests/workspace/test_c4_source.py \
  tests/workspace/test_c4_render.py::test_real_pinned_renderer_publishes_one_validated_handoff_and_cache
```

Named coverage included
`test_receipt_retry_refreshes_registered_room_move_incarnation` (current
acknowledgement and room-move mapping, with an immediate projection read),
`test_public_mapping_commit_holds_fence_across_rewrite` (atomic routing),
`test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor`
(positive UTF-8 continuation),
`test_execution_start_is_committed_before_held_executor_finishes` (held-executor
operational boundary), and the new per-statement remaining-budget fixtures. The
latter observed 8 publisher schema refreshes, 11 transcript schema/commit
refreshes and 12 read-only schema/routing refreshes, with each configured busy
timeout strictly smaller than the preceding value under a deterministic
monotonic clock.

Git ancestry at that revision contains Feature Task 1 and the Feature plan at
`4959f09f`; `git merge-base --is-ancestor 4959f09f afc7579a` succeeded. The
separately reported Feature 3/4 integration revision `9affeb7f` is not an
ancestor of this Task branch. Its reported 75-pass/1-fail run and isolated pass
for the room-move projection fixture are therefore context, not evidence claimed
by this checkout; the same fixture passed here as part of the 92-test command.

## Remaining limits and handoff

The contention measurements do not bound an already admitted filesystem open,
source read, JSONL append or fsync. The two historical reconstruction assertions
remain a separate stale-baseline concern and were not relaxed. Final Feature and
Epic acceptance, publication recovery and completed-record correction remain
with their existing owners. The Task lifecycle message carries the exact final
commit and supervised validation result to the owning Feature and the dependent
Feature 3 team.

## Review conflict resolution on the integrated Feature branch

The Feature branch was rebased onto the Epic branch containing the Recovery
Progress design ownership correction and Feature 3's Historical/current-progress
Code nodes. The Recovery Progress evidence row now states the measured contention
coverage and admitted filesystem limit. The Dashboard Code view retains both UI
nodes and the existing-index source node; the War Room design retains both the
Historical polling contract and the bounded writer/lookup contract.

On that rebased tree, the focused publisher, milestone, durable-store, recovery
and transcript API, held-executor, source-contract and real-render/cache command
listed above passed 94 tests in 136.67 s. A separate regression now forces the
first fast-path dirty publication to reach its deadline after the mapping commit.
It observes no `current.json` pointer, then proves that a later drain publishes
the same milestone reference and replay keeps one transcript line. The new test
and the room-move mapping test passed together (2 tests in 1.21 s); `ruff check`
on the changed test file and `git diff --check` passed. The room-move test alone
does not prove expiry followed by drain.
