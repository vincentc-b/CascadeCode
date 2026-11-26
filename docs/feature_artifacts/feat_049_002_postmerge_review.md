# Post-merge transcript review

Reviewed the merged transcript implementation at `7f7df0e8` against the Feature
receipt-retry, bounded-detail and architecture acceptance gates. The Feature
record had already moved to completed before this review.

Two focused reproductions exposed gaps:

- A delayed private publisher acknowledgement could replace a newer stored
  incarnation and append sequence. The public mapping test did not cover this
  private fast-path and drain helper.
- A caller-edited detail cursor starting inside a UTF-8 character returned an
  empty chunk and a continuation at the same offset.

The repair rechecks the current fenced source acknowledgement when an existing
receipt's routing tuple changes. It preserves immutable receipt, entry, graph
and message conflict checks. The detail reader rejects a continuation inside a
UTF-8 character as `400 invalid_request`. The regressions exercise the private
mapping helper after a rewrite and the loopback detail route with a malformed
cursor.

Design review: `cascade/war_room/DESIGN.md` and `cascade/watchdog/DESIGN.md`
describe the current read and mapping behavior. `cascade/workspace/DESIGN.md`,
`cascade/task/DESIGN.md`, `cascade/DESIGN.md`, `DESIGN.md`, and the pinned
`model.dsl`, `views.dsl` and `workspace.contract.json` were checked for affected
interfaces. Context, container and component ownership remain unchanged. Native
Dashboard and Watchdog Code nodes still name the same real functions; the repair
changes behavior inside those functions and no source symbol or relationship.
The normal route uses a current fenced acknowledgement; the delayed route now
refreshes from current source before updating stored routing. Detail reads stay
projection-only, with malformed UTF-8 offsets rejected before returning a chunk.

Verification: the integrated milestone, transcript API and source-contract suite
passed 27 tests with the 10,000-row and browser cases deselected because their
affected behavior is covered by the focused route tests. Ruff and `git diff
--check` passed. Task 4 reported 88 supervised checks and a pinned render/browser
journey before this repair; those reports are not new post-repair browser evidence.
The completed Task 1 and Task 5 board-record corrections remain an independent
authorized-board issue. This artifact does not change the canonical Feature or
Task lifecycle records.

## Architecture review after the repair

Reviewed the final `ecd390f4` diff against `cascade/war_room/DESIGN.md`,
`cascade/watchdog/DESIGN.md`, `cascade/workspace/DESIGN.md`,
`cascade/task/DESIGN.md`, `cascade/DESIGN.md`, `DESIGN.md`, and the pinned
`model.dsl`, `views.dsl` and `workspace.contract.json`. The War Room design owns
the detail-cursor failure behavior and fenced transcript routing rule; Watchdog
owns the private publisher mapping and its restart path. The source and designs
agree that a stale receipt may update mutable routing only from the current
fenced acknowledgement, while receipt, entry, graph and message identities remain
fixed. A malformed detail offset fails before any nonadvancing page is returned.

Diagram impact by level: `cascade-context` and `cascade-containers` retain their
actor, runtime and persistence boundaries; `cascade-war-room-components` and
`cascade-supervisor-components` retain their ownership and interfaces. The
native `cascade-dashboard-code` and `cascade-watchdog-code` views already name
the affected real Function symbols. The `resume_transcript_room_move` Code node
and retirement relationship are present in the final model and view contract.
This repair changes behavior inside those symbols, so no model element, source
link or relationship needs revision. The War Room normal/crash and move-resume
sequences, plus the Watchdog after-lock/replay sequence, still trace to source.

Local verification after the repair: 29 focused milestone, transcript API and
C4 source tests passed; `validate_c4_workspace` accepted 234 elements, 280
relationships and 24 views; Ruff and `git diff --check` passed. The final source
contract resolves the affected Code symbols. Task 4's earlier pinned render and
Chromium navigation covered context → containers → component → Code, Level up,
deep-link restoration, pinned source, warm reuse and render bounds on the same
model revision. The repair changed no C4 source, so that navigation evidence
still applies; it was not rerun after `ecd390f4`. The final architecture
publication/accepted-lineage state is left for the Epic's authorized review;
this local evidence does not claim product-trunk integration.
