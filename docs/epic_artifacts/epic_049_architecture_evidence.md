# Epic 049 architecture planning review

## Reviewed decision and scope

The canonical Epic spec owns the proposed progress, source-receipt, liveness,
transcript append/replay and bounded history contract (dec_004–dec_007). All three
backlog Feature specs were read and updated through Cascade; their required Task
acceptance now includes that contract. Runtime progress/milestones are not
implemented by this planning pass. No child was dispatched, dependency installed,
external message sent, or accepted architecture snapshot rewritten.

Current implementation coverage is committed in the owned integration branch.
`model.dsl`, `views.dsl` and `workspace.contract.json` contain 13 additional real
Function nodes, nine code relationships, component design links and current
Dashboard responsibility wording. Source ownership is bound to this proposal.
Model inventory: 209 elements, 241 relationships, 24 views.

A concrete UI blocker was fixed during review: default full-model snapshot
metadata measured 271,703 bytes against the existing 262,144-byte cap. A one-view
page measured 247,548 bytes. Offline diagnostic sizing captured these values;
no oversized response was served and no production cap was raised. The HTTP
route now reduces the view page, preserves all targets and emits advancing
continuation. The document-context consumer follows continuation as well.
Metadata plus one view that cannot fit still returns HTTP 413. This is the only
product behavior changed during planning.

## Design and diagram impact reconciliation

| Level / views | Review and result |
|---|---|
| `cascade-landscape`, `cascade-context` | Root context remains accurate: same operator, local system, repository, provider and forge. No topology change. |
| `cascade-containers` | Root and package runtime/storage boundaries remain accurate; transcript helpers are in-process library code, not a new deployed service. |
| `cascade-supervisor-components`, `cascade-team-components`, `cascade-war-room-components` | Preserved component ownership; clarified Dashboard responsibilities and added direct links to War Room, Task, Watchdog and Workspace designs. |
| `cascade-dashboard-code` | Added routing-based recovery summary, selection, chat GET/read/append, post-turn mirror and explicit backfill functions. War Room design documents their actual coarse-state/full-read/thread-only-lock limits. |
| `cascade-task-code` | Added owner acknowledgement, attempt claim, checkpoint and finalization functions; Task design shows locked state, external execution and interrupted-claim recovery. |
| `cascade-workspace-code` | Added graph invocation and process-local owner observation. Workspace design distinguishes queued ownership from executing attempts and links the transcript handoff sequence. |
| `cascade-watchdog-code`, `cascade-teams-code` | Existing receipt, exact-generation postcheck and publication nodes still describe current code. No new producer is implemented here. Feature tasks own the proposed notification/drain/liveness updates. |
| `cascade-architecture-browser-code` | Existing `snapshot_projection` node and browser/API relationship cover the bounded page-sizing correction. Its internal helper and document-context continuation remain within that responsibility; no additional component, Code view or render process is introduced. |
| Behavioral diagrams | War Room adds graph-return and interruption/backfill sequence; Task adds attempt/claim lifecycle. Workspace and package link to these owners rather than duplicate them. Proposed crash matrix and live progress sequence remain in the Epic spec. |

Reviewed changed designs: `cascade/DESIGN.md`, `cascade/war_room/DESIGN.md`,
`cascade/task/DESIGN.md`, `cascade/workspace/DESIGN.md`. Reviewed affected root
context/audit/container sections and Watchdog producer/postcheck interfaces.
Removed stale War Room baseline inventory and historical phrasing. Added stable
local transcript, action-evidence and turn-evidence requirement/decision IDs in
exactly one owning design each. All local file links and heading anchors in the
four changed designs resolve; 13 added Function declaration kinds and symbols
were checked using Python AST against their real source files. No new directory
boundary was created. Source contract validation passed.

## Inspectable checks

- `python -m pytest -q tests/workspace/test_c4_source.py tests/war_room/test_recovery_incident_projection.py tests/war_room/test_planning_transcript.py tests/war_room/test_chat_poll_routing.py tests/war_room/test_projection_batching.py`: **29 passed in 2.86s**.
- Final `python -m pytest -q tests/war_room/test_architecture_http.py --tb=short`: **13 passed in 15.66s**. The expanded HTTP scenario verifies smaller pages, every view exactly once, preserved targets, advancing cursors, later-page document context and minimum-page refusal. Existing cases verify forged resources and selections, missing/stale references, and pinned source surviving replacement/deletion of the original function in the newer checkout.
- C4 metadata tests reject invalid component ownership and escaping source paths. No existing symbol was renamed or removed by this diff; new symbols and their single Code owners were resolved against source.
- The pinned Docker/Structurizr renderer produced all **24 interactive views**. The model/source revision used in the final browser journey is `01e1cff36a48b8abe3771708936921a93bc83643`. Runtime route code at that commit includes both pagination fixes. A subsequent test-only commit corrects the artificial fixture's selected-context byte allowance; later planning prose does not change the tested route or modeled functions.
- The default renderer retains its **180-second** deadline and existing memory/CPU/PID bounds. A cold render at `dfcc7f9c79926c2bddd673d1f8599482a3670680` took **45.47s**; reproducing the final pinned artifact from cache took **0.54s**. These are local observations, not latency promises.
- [Reproducible Chromium smoke](epic_049_architecture_browser.py) and [captured results](epic_049_architecture_browser.json): real production architecture routes, real rendered SVGs, and default request paging. Unrelated operational-panel requests are stubbed to avoid inspecting other teams; no architecture endpoint or result is mocked. All three paths traverse context → container → component → Code, restore a target deep link, open pinned source and Level up. Covered `append_planning_turn_to_chat`, `_claim_resume_attempt`, and `graph_turn_owner_is_live`. **No architecture HTTP errors** were observed. Initial cold browser readiness was **66.16s**; paths including reload/source/context requests took **8.92s**, **8.33s**, and **12.46s**. Render-operation count stayed **3 → 3** across navigation. Reload/close can cancel in-flight HTTP responses and produce server BrokenPipe diagnostics; there were no failed completed architecture responses.
- `git diff --check` passed. No full repository suite was claimed or required.

## Normal and interruption traces

Normal current path: a routed owner enters supervision and
`acknowledge_team_recovery` commits its matching acknowledgement;
`resume_action` claims an attempt under the lifecycle lock, releases the critical
section before the executor, and finalizes its result. Independent Watchdog
postcheck, not publication or attempt success, proves resolution. After the graph
returns, `_invoke_role_turn` forwards the new saved messages to the transcript
writer. Existing board projection may still call queued work investigating;
the proposed producer is required to replace that coarse display semantics.

Failure/current restart: a crash can leave a durable open attempt and checkpoint,
while process-local queues/locks disappear. Review-publication reconciliation
uses exact process identity; unknown ownership is not death. A checkpoint-to-chat
gap is repaired only by explicit sync, whose author/body deduplication and
thread-only locking have documented limits. These facts justify the proposed
source receipts, graph fence, pending append intent and stable message identity.
No test in this planning review claims the proposed crash matrix already passes.

## Limits and handoff

The proposed live progress, two-process transcript protocol, legacy import,
room movement and operational recovery timeline remain Feature implementation
acceptance, with exact Task obligations in the Epic and child specs. Large target
metadata that cannot fit even one view still fails explicitly; this correction
does not introduce target pagination or claim arbitrary model scalability.
Related epics' scoped historical records and accepted review ancestry were not
established; current local code and the supplied timeline are the evidence basis.
No production deployment or provider/forge recovery was exercised.

The exact publication request is retained in
[epic_049_architecture_review.json](epic_049_architecture_review.json).
An empty accepted lineage for `epic:epic_049` was read from the canonical store;
publication therefore uses generation `null`. Publication status and architect
sign-off are authoritative in Cascade. If publication returns pending, replay
that identical request on a later turn; do not substitute newer unreviewed pins.
The Epic Manager must review and sign off on the final plan revision separately.
