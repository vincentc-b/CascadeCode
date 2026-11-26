# Contention architecture planning review

The committed feature plan at `a90648ca8033e8e4ce63acf099a994a702763852`
assigns the shared deadline and replay correction to `task_049_005_001`, followed
by integrated design, Code view and browser verification in `task_049_005_002`.
This planning branch changes work records only. The current source and design
remain the baseline for implementation, so the planning publication has
`no_diagram_change` impact. This does not assert that the contention behavior
or the current bound claim is verified.

## Task-to-criterion mapping

| Binding criterion | Owning task and acceptance evidence |
|---|---|
| One monotonic 250 ms fast-path or caller-selected drain deadline across preceding append/dedup, public/private publisher transaction, thread lock, OS graph fence and SQLite work | `task_049_005_001` requires remaining-budget propagation from all three entry points, no timeout reset, measured bounds and the uninterruptible filesystem/source limitation. `task_049_005_002` checks the integrated revision and records the exact results. |
| Existing-index-only source acknowledgement and pending replay on missing, incompatible, unfinished or contended evidence | `task_049_005_001` requires a read-only compatible index lookup, no initialization/import/repair/publication, no lost receipt or advanced cursor, and exactly-once later drain. |
| Publisher-before-graph ordering and graph fence through first mapping insert and later commits, including delayed private/public writers | `task_049_005_001` requires the transaction and fence order, immutable identity checks, current incarnation/sequence and interleaving/rewrite/move/restart regressions. |
| Real thread, second-process flock and SQLite contention, with elapsed-time tolerances and replay | `task_049_005_001` owns deterministic integration cases and named timing evidence; `task_049_005_002` re-runs them at the integrated revision. Existing Feature 4 tests are baseline evidence only. |
| Recovery Progress claim, normal/pending/restart flows and one-owner design mapping | `task_049_005_002` owns `REQ-RECOVERY-PROGRESS-004`, `architecture/design-mappings.json`, affected Recovery Progress/War Room/Watchdog/package/Workspace designs, source-linked flows and no historical attribution in designs. |
| All-level diagrams, native Watchdog/Dashboard Code and source contract | `task_049_005_002` owns final-diff impact decisions for context, containers, components, Code and behavior; model/contract sync, source-contract/render validation, Explore/Level up/deep-link/pinned-source checks and measured warm reuse. |
| Final integrated acceptance and handoff | `task_049_005_002` records the repaired revision, named focused tests, timing limits, design paths and gaps for the Epic and Feature 3 final gate. Publication recovery and completed-record correction remain with the Epic. |

## Diagram impact inventory

| Level and view | Owning design and source | Integrated update and check |
|---|---|---|
| Landscape and context: `cascade-landscape`, `cascade-context` | Root `DESIGN.md`; existing operator and repository boundaries | Task 2 checks the final diff. No topology change is proposed; record a specific reason if unchanged. |
| Containers: `cascade-containers` | Root and `cascade/DESIGN.md`; publisher SQLite and transcript JSONL/index | Task 2 verifies runtime and persistence boundaries and avoids an OS isolation claim. |
| Components: `cascade-supervisor-components`, `cascade-war-room-components` | `cascade/watchdog/DESIGN.md`, `cascade/recovery_progress/DESIGN.md`, `cascade/war_room/DESIGN.md` | Task 2 traces Watchdog drain, publisher mapping and War Room fenced lookup, including timeout to pending. |
| Integrated Code: `cascade-watchdog-code`, `cascade-dashboard-code`; `cascade-workspace-code` if ownership resolution changes | `publisher.py` entry points and private mapping helper; `recovery_milestones.py` append; `chat_store.py` graph fence, existing-index lookup and relevant owner resolution | Task 2 reconciles real symbols, kinds, relationships and source paths in `model.dsl`, `views.dsl` and `workspace.contract.json`. It validates source links, render, Explore, Level up, deep links, pinned source and warm reuse. |
| Behavior | Recovery Progress and War Room designs | Task 2 traces normal publisher-before-graph commit, deadline exhaustion to pending, and restart/replay against the integrated code and contention fixtures. |

## Current source and design review

Reviewed `DESIGN.md`, `cascade/DESIGN.md`,
`cascade/recovery_progress/DESIGN.md`, `cascade/war_room/DESIGN.md`,
`cascade/watchdog/DESIGN.md`, `cascade/workspace/DESIGN.md`, and
`architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`.
The Recovery Progress and War Room designs link the relevant source entry points
and show the normal publisher transaction, graph fence, commit, pending and
restart paths. The package and Workspace designs link to the owning Code views.
There are no `DESIGN.md` edits in the planning diff.

The current `graph_transcript_fence` waits on a process thread lock and blocking
OS `flock`; `fenced_transcript_source_acknowledgement` calls `_connect_index`,
which opens SQLite with a 30-second timeout and runs schema statements. The
publisher starts its 250 ms clock before append but does not pass the remaining
budget through append, lock acquisition and the fenced lookup. Its drain has
the same acquisition gap before its loop checks the deadline. These source
facts support the Task 1 correction. `REQ-RECOVERY-PROGRESS-004` currently says
the fast path and drain are verified against configured bounds; Task 2 must
reconcile that verification claim with measured lock contention and the
uninterruptible filesystem/source baseline limit.

`architecture/design-mappings.json` currently maps
`cascade/recovery_progress` to `cascade/DESIGN.md` even though the directory
has its own meaningful `DESIGN.md`. Task 2's revised acceptance criteria explicitly
require correcting the mapping and verifying architecture resource discovery and
pinned links alongside the final model/design update. The active Task 1 record has
substantive criteria under a second `Acceptance criteria` heading inside
`Implementation notes`, while its template acceptance heading remains `TBD`;
its live implementation criteria are explicit, and this record is left for the
task delivery process to correct. The backlog Task 2 acceptance criteria name
the integrated design and navigation gates.

`/opt/conda/bin/python3.12 -m pytest -q tests/workspace/test_c4_source.py`
passed (14 tests). `git diff --check` is the publication safeguard. This source
contract result describes the current model only. Task 1 supplies measured
contention tests; Task 2 must re-run them at the integrated revision and verify
the browser path and source opening before final acceptance. No local render or
browser check was run for this unchanged planning model.

Cascade published the exact pinned request in
`feat_049_005_architecture_review.json` as `no_diagram_change`:
operation `architecture-publication-9e884573f9a9e82b271bd8ae543b5c8bd91220ffbb670b6e6e7ff44095ec928e`,
review unit
`architecture-review-70fc083c1b5a21b1a76147edd4cedf76381446927c7f681653215465d69d4196`.
