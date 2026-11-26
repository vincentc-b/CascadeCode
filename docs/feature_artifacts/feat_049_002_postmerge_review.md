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
