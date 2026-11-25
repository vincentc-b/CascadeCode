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

## Epic Manager final planning review

Reviewed plan `032809336f3fcf3810c7270c28195da9c85a3bf6` and read all three
backlog Feature specs through Cascade. The three sequential slices cover the
eight success criteria without adding repair authority, a scheduler or paid
commentary turns. Feature scope carries the selected receipt, liveness, replay,
read-budget and diagram obligations into required Task acceptance. Concrete
Feature APIs and Tasks remain normal child planning work, not completed work.

Reviewed the four changed designs listed above against the final diff, the root
context/audit contract and the Watchdog verification boundary. Current-code
claims agree with `resume_action`, `graph_turn_owner_is_live` and
`_invoke_role_turn`: claim/preflight is locked, execution occurs outside that
critical section, queued owner evidence is not execution proof, and current
authored transcript mirroring follows graph return. An interrupted attempt and
the checkpoint-to-chat gap remain distinct recovery cases. No further design
edit is needed: proposed progress and append protocols stay in work records.
The level-by-level inventory above and the Epic inventory assign implementation
updates and verification to the three Feature teams, including integrated Code
views and normal/failure/restart scenarios.

Independent checks on the reviewed checkout:

- `python -m pytest -q tests/workspace/test_c4_source.py tests/war_room/test_architecture_http.py`:
  **27 passed in 9.94s**.
- `validate_c4_workspace` returned `C4WorkspaceContract`.
- All five saved design/model/contract references match their committed SHA-256
  digests and current checkout bytes; no reviewed pin was replaced.
- Inspected the saved Chromium journey and results: three context-to-Code,
  pinned-source, deep-link and Level-up paths passed, with render-operation
  count unchanged. This review did not repeat the browser run or claim new
  product acceptance.
- Read-only epic comment enumeration returned no threads; Cascade returned no
  architecture amendments. All three Features remain in backlog with the
  declared dependency order.

Manager review is complete; role sign-off is recorded separately by Cascade.
Architecture publication remains pending and must be resumed by the Epic
Architect with the identical saved request. `cascade/agent/mcp_wrappers.py`
explicitly withholds `publish_architecture_review` from Epic Manager sessions;
this review did not bypass that role boundary. The runtime implementation,
crash matrix, operational recovery fixture and scoped historical-provenance
limits above remain open delivery obligations, not plan-review failures.

## Architect publication replay outcome

Replayed the identical saved request after canonical `read_doc` confirmed plan
revision `032809336f3fcf3810c7270c28195da9c85a3bf6`. Cascade returned **failed**,
reason `internal_error`: "render worker was interrupted after its automatic
recovery attempt". No review unit or amendment was created by this operation.

- Publication operation: `architecture-publication-9b870c091d516f233c9a27d0b7d088f4770c7fe0c753343719515962f238776e`.
- Render operation: `c4-render-e33148f7d2456ca7b316d71b615a7588cfb5e2fd884a335fcdff3bb5e44c5a5e`.
- Reviewed tuple: `708549cdf023f9f691aa4b2632671c3bb09b8e29a83f0b30ceef64ba4778c51f`.

This result supersedes the pending status recorded above. The saved request,
generation, plan, design and model pins remain unchanged. Verified all five
design/model/contract references against both committed SHA-256 digests and
checkout bytes; reviewed the four changed designs and their affected interfaces
against the planning diff and the existing level-by-level inventory. No further
design change is needed for an interrupted render worker. `git diff --check`
passed. Existing test/browser evidence above remains applicable; no new test or
browser run is claimed for this replay.

Runtime recovery handoff: inspect the publication and render operations above
and provide a supported retry that preserves their failure history and exact
reviewed tuple. `discover_architecture_publication` returns terminal publication
rows without scheduling work, so repeating this failed request cannot restart
the renderer. The Architect's available Cascade tools expose publication but no
failed-publication retry. No direct ledger edit, accepted-snapshot rewrite,
replacement proposal or runtime restart was attempted. Both plan sign-offs remain
on the same revision; architecture publication is still incomplete.
